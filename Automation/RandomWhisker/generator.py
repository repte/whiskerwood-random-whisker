"""Author Random Whisker. Run inside the modkit editor.

The editor-only helper adds one bridge function that calls the game's native
Arco_SpawnAgentsAtDock on the live player controller. No runtime DLL ships.
"""
import json
from functools import lru_cache
from pathlib import Path
import re
import runpy

import unreal
import toolset_registry
from editor_toolset.toolsets.blueprint import BlueprintTools as BP
from editor_toolset.toolsets import blueprint_dsl


ROOT = "/Game/Mods/RandomWhisker"
VERSION = "0.1.0"
BRIDGE = "RwSpawnAtDock"
HERE = Path(__file__).resolve().parent
LABELS = {"en": "Spawn a random Whisker", "de": "Zufälligen Whisker erzeugen"}
native = lambda name: unreal.load_class(None, "/Script/ProjectArco." + name)
g = lambda name: f"(Variables|Default|Get{name})"
put = lambda name, value: f"(Variables|Default|Set{name} {value})"
valid = lambda value: f"(CallFunction|HasObject :Object {value})"


def clear_body(graph):
    kept_result = False
    for node in BP.find_nodes(graph):
        kind = node.get_class().get_name()
        if kind == "K2Node_FunctionEntry":
            continue
        if kind == "K2Node_FunctionResult" and not kept_result:
            kept_result = True
            for pin in BP.get_node_infos([node])[0].input_pins:
                for other in pin.connected_pins:
                    BP.break_pins(other, pin.pin_id)
            continue
        BP.delete_node(node)


with toolset_registry.tool_raising_exceptions():
    access = json.loads(unreal.RandomWhiskerAuthoring.enable_authoring())
    assert access.get("success"), access
    bp = unreal.load_asset(ROOT + "/BP_MapLoad")
    if bp is None:
        bp = BP.create(ROOT, "BP_MapLoad", unreal.Actor.static_class())
    assert BP.get_parent(bp) == unreal.Actor.static_class()
    for kind, names in {"bool": "ShuttingDown HasClock HasSpawnClock",
                        "real": "LastPoll LastSpawn", "string": "CurrentLanguage"}.items():
        for name in names.split():
            if name not in BP.list_variables(bp):
                BP.add_variable(bp, name, kind)

    definitions = {
        "HasObject": [("Object", unreal.Object.static_class())],
        "Ready": [], "SpawnOne": [], "Pump": [], "Shutdown": [],
        "CreatePanel": [], "RefreshLanguage": [], "SyncPanelVisibility": [],
        "HudAllowsDisplay": [("InputHud", native("PlayHud")),
                             ("InputController", native("PlayerController_Play"))],
    }
    graphs = {}
    existing = {str(graph.get_name()) for graph in BP.list_graphs(bp)}
    for name, params in definitions.items():
        graph = BP.get_graph(bp, name) if name in existing else BP.add_function_graph(bp, name)
        graphs[name] = graph
        if name not in existing:
            for param, kind in params:
                if isinstance(kind, str):
                    BP.add_function_param(graph, param, kind, True)
                else:
                    BP.add_object_function_param(graph, param, kind, True)
            BP.add_function_param(graph, "Result", "bool", False)
        clear_body(graph)
    if BRIDGE in existing:
        BP.remove_function_graph(bp, BRIDGE)
    report = json.loads(unreal.RandomWhiskerAuthoring.add_runtime_bridge(bp))
    assert report.get("success"), report
    unreal.log("RANDOMWHISKER_BRIDGE " + json.dumps({k: v for k, v in report.items() if k != "bridge_bytecode"}))
    BP.compile_blueprint(bp)
    assert unreal.EditorAssetLibrary.save_loaded_asset(bp)

    runpy.run_path(str(HERE / "generate_ui.py"), run_name="__main__")
    panel_class = unreal.load_class(None, ROOT + "/WBP_RandomWhisker.WBP_RandomWhisker_C")
    assert panel_class, "Widget class missing"
    if "Panel" not in BP.list_variables(bp):
        BP.add_object_variable(bp, "Panel", panel_class)
    BP.compile_blueprint(bp)

    context = graphs["Pump"]
    nodes = list(dict.fromkeys(BP.find_node_types(context, "", [])))
    normalize = lambda value: re.sub("[^a-z0-9]", "", str(value).lower())

    @lru_cache(maxsize=None)
    def node(method, owner=None):
        matches = [item for item in nodes
                   if normalize(item.rsplit("|", 1)[-1].split("(", 1)[0]) == normalize(method)]
        if owner:
            matches = [item for item in matches if any(
                normalize(pin.type_id) == normalize(owner) + "objectreference"
                for pin in BP.get_node_type_pins(context, item).input_pins
                if pin.name in ("self", "Target"))]
        preferred = [item for item in matches if not item.startswith("Class|")]
        matches = preferred or matches
        assert len(matches) == 1, (method, owner, matches)
        return matches[0]

    def invoke(method, owner, target, args=""):
        return f"({node(method, owner)} :self {target} {args})"

    def unpack(struct, value, prefix):
        kind = "Utilities|Struct|Break" + struct
        names = [prefix + str(pin.name) for pin in BP.get_node_type_pins(context, kind).output_pins]
        return f"(bind ({' '.join(names)}) ({kind} {value}))"

    panel_call = lambda fn, args="": invoke(fn, "WBPRandomWhisker", g("Panel"), args)
    hidden = panel_call("ApplyGameplayVisibility", ":Visible false")
    enum_patches = {"Ready": ["DONE"], "SyncPanelVisibility": ["DONE"]}
    code = {}
    code["HasObject"] = '(fn HasObject (Object) (Utilities|IsValid Object (:"Is Valid" (return true)) (:"Is Not Valid" (return false))))'
    code["Ready"] = f'''(fn Ready ()
        (if {g('ShuttingDown')} (return false))
        (bind mode (Utilities|Casting|CastToProjectArcoGameModeBase :Object (Game|GetGameMode))
          (:then
            (bind phase (Class|ProjectArcoGameModeBase|CurrentInitPhase :self mode))
            (if (not (Utilities|Enum|Equal(Enum) :A phase)) (return false))
            (bind (found systems) (Class|ArcoSystems|GetArcoSys))
            (if (or (not found) (not {valid('systems')})) (return false))
            (if (not (Class|ArcoSystems|IsLive :self systems)) (return false))
            (bind player (Utilities|Casting|CastToPlayerController_Play :Object (Game|GetPlayerController :PlayerIndex 0))
              (:then
                {unpack('ArcoPlayerState', '(Class|PlayerControllerPlay|GetMState :self player)', 'ps_')}
                (if ps_m_showReplayMenu (return false))
                (return true))
              (:CastFailed (return false))))
          (:CastFailed (return false))))'''
    code["HudAllowsDisplay"] = f'''(fn HudAllowsDisplay (InputHud InputController)
        (if (or (not {valid('InputHud')}) (not {valid('InputController')})) (return false))
        (if (not (Class|PlayHud|GetMUiHasFadedIn :self InputHud)) (return false))
        {unpack('ArcoPlayerState', '(Class|PlayerControllerPlay|GetMState :self InputController)', 'p_')}
        (if (or {valid('p_activeArcoView')} (or (not p_m_showHud) (or p_m_dev_hideAllHud p_m_showReplayMenu))) (return false))
        {unpack('HudState', '(Class|PlayHud|GetMHudState :self InputHud)', 'h_')}
        (if h_showSaving (return false))
        {unpack('VisibilityToggles', 'h_sectionVisibilities', 'v_')}
        (return v_showHudRoot))'''
    code["SyncPanelVisibility"] = f'''(fn SyncPanelVisibility ()
        (if (not {valid(g('Panel'))}) (return false))
        (bind mode (Utilities|Casting|CastToProjectArcoGameModeBase :Object (Game|GetGameMode))
          (:then
            (bind phase (Class|ProjectArcoGameModeBase|CurrentInitPhase :self mode))
            (if (or {g('ShuttingDown')} (not (Utilities|Enum|Equal(Enum) :A phase))) {hidden} (return false))
            (bind (found systems) (Class|ArcoSystems|GetArcoSys))
            (if (or (not found) (not {valid('systems')})) {hidden} (return false))
            (if (not (Class|ArcoSystems|IsLive :self systems)) {hidden} (return false))
            (bind player (Utilities|Casting|CastToPlayerController_Play :Object (Game|GetPlayerController :PlayerIndex 0))
              (:then
                (bind visible (CallFunction|HudAllowsDisplay
                  :InputHud (Class|PlayerControllerPlay|GetMPlayHud :self player) :InputController player))
                {panel_call('ApplyGameplayVisibility', ':Visible visible')}
                (return visible))
              (:CastFailed {hidden} (return false))))
          (:CastFailed {hidden} (return false))))'''
    code["RefreshLanguage"] = f'''(fn RefreshLanguage ()
        (if (not {valid(g('Panel'))}) (return false))
        (bind manager (Class|Backbone|GetLocManager))
        (if (not {valid('manager')}) (return false))
        (bind language (Utilities|String|ToLower (Utilities|String|ToString(Name) (Class|LocManager|GetActiveLanguage :self manager))))
        (if (Utilities|String|EqualExactly(String) language {g('CurrentLanguage')}) (return true))
        {put('CurrentLanguage', 'language')}
        (if (Utilities|String|StartsWith :SourceString language :InPrefix "de")
          {panel_call('SetLabel', ':Label ' + json.dumps(LABELS['de']))} (return true))
        {panel_call('SetLabel', ':Label ' + json.dumps(LABELS['en']))}
        (return true))'''
    code["CreatePanel"] = f'''(fn CreatePanel ()
        (if {valid(g('Panel'))} (return true))
        (bind player (Game|GetPlayerController :PlayerIndex 0))
        (if (not {valid('player')}) (return false))
        (bind widget (UserInterface|CreateWidget :Class "{ROOT}/WBP_RandomWhisker.WBP_RandomWhisker_C" :OwningPlayer player))
        (if (not {valid('widget')}) (return false))
        {put('Panel', 'widget')}
        {invoke('SetHost', 'WBPRandomWhisker', 'widget', ':Host self')}
        {invoke('AddToViewport', 'UserWidget', 'widget', ':ZOrder 35')}
        {put('CurrentLanguage', '""')}
        (CallFunction|RefreshLanguage)
        (CallFunction|SyncPanelVisibility)
        (return true))'''
    # One click spawns one Whisker. The short real-time gate absorbs double clicks.
    code["SpawnOne"] = f'''(fn SpawnOne ()
        (bind ready (CallFunction|Ready)) (if (not ready) (return false))
        (bind now (Utilities|Time|GetRealTimeSeconds))
        (if (and {g('HasSpawnClock')} (and (>= now {g('LastSpawn')}) (< (- now {g('LastSpawn')}) 0.25))) (return false))
        {put('HasSpawnClock', 'true')} {put('LastSpawn', 'now')}
        (bind player (Utilities|Casting|CastToPlayerController_Play :Object (Game|GetPlayerController :PlayerIndex 0))
          (:then (CallFunction|{BRIDGE} :Controller player) (return true))
          (:CastFailed (return false))))'''
    code["Pump"] = f'''(fn Pump ()
        (if {g('ShuttingDown')} (return false))
        (CallFunction|SyncPanelVisibility)
        (bind now (Utilities|Time|GetRealTimeSeconds))
        (if (and {g('HasClock')} (and (>= now {g('LastPoll')}) (< (- now {g('LastPoll')}) 1.0))) (return false))
        {put('HasClock', 'true')} {put('LastPoll', 'now')}
        (bind ready (CallFunction|Ready)) (if (not ready) (return false))
        (bind made (CallFunction|CreatePanel)) (if (not made) (return false))
        (CallFunction|RefreshLanguage) (return true))'''
    code["Shutdown"] = f'''(fn Shutdown ()
        {put('ShuttingDown', 'true')}
        (if {valid(g('Panel'))} (Widget|RemovefromParent :self {g('Panel')}))
        (return true))'''

    for name, source in code.items():
        blueprint_dsl.parse(source)
        clear_body(graphs[name])
        unreal.log("RANDOMWHISKER_WRITE " + name)
        BP.write_graph_dsl(graphs[name], source)
        if name in enum_patches:
            comparisons = [item for item in BP.get_node_infos(BP.find_nodes(graphs[name]))
                           if item.type_id == "Utilities|Enum|Equal(Enum)"]
            assert len(comparisons) == len(enum_patches[name]), (name, len(comparisons))
            for comparison, literal in zip(comparisons, enum_patches[name]):
                BP.set_pin_value(next(pin.pin_id for pin in comparison.input_pins if pin.name == "B"), literal)
    BP.write_graph_dsl(BP.get_graph(bp, "EventGraph"), '''
        (event EventBeginPlay () (CallFunction|Pump))
        (event EventTick (DeltaSeconds) (CallFunction|Pump))
        (event EventEndPlay (EndPlayReason) (CallFunction|Shutdown))''')
    BP.compile_blueprint(bp, warnings_as_errors=True)
    cdo = unreal.get_default_object(bp.generated_class())
    cdo.set_editor_property("hidden", True)
    tick = cdo.get_editor_property("primary_actor_tick")
    tick.set_editor_property("start_with_tick_enabled", True)
    tick.set_editor_property("tick_even_when_paused", True)
    tick.set_editor_property("tick_interval", 0.0)
    cdo.set_editor_property("primary_actor_tick", tick, notify_mode=unreal.PropertyAccessChangeNotifyMode.NEVER)
    assert unreal.EditorAssetLibrary.save_loaded_asset(bp)
    widget = unreal.load_asset(ROOT + "/WBP_RandomWhisker")
    BP.compile_blueprint(widget, warnings_as_errors=True)
    assert unreal.EditorAssetLibrary.save_loaded_asset(widget)

    descriptor_path = HERE.parents[1] / "Content" / "Mods" / "RandomWhisker" / "RandomWhisker.uplugin"
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8-sig"))
    assert descriptor["Name"] == "RandomWhisker" and descriptor["Version"] == VERSION, descriptor
    destination = Path(unreal.Paths.project_content_dir()) / "Mods" / "RandomWhisker" / "RandomWhisker.uplugin"
    if destination.resolve() != descriptor_path.resolve():
        destination.write_bytes(descriptor_path.read_bytes())
    Path(unreal.Paths.project_saved_dir(), "RandomWhisker-Runtime.dsl").write_text("\n\n".join(code.values()), encoding="utf-8")
unreal.log("RANDOMWHISKER_GENERATED_PASS")
