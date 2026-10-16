"""Generate the Random Whisker HUD button. Run after BP_MapLoad declares SpawnOne."""
import re

import unreal
import toolset_registry
from editor_toolset.toolsets.blueprint import BlueprintTools as BP
from editor_toolset.toolsets import blueprint_dsl


ROOT = "/Game/Mods/RandomWhisker"
NAME = "WBP_RandomWhisker"
LABEL = "Spawn a random Whisker"
UMG = unreal.get_default_object(unreal.UMGToolSet)
HOST = unreal.load_class(None, ROOT + "/BP_MapLoad.BP_MapLoad_C")
assert HOST, "Declare the Random Whisker host first"


def color(value):
    rgb = [int(value[index:index + 2], 16) / 255.0 for index in (0, 2, 4)]
    linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
    return unreal.LinearColor(*linear, 1.0)


GOLD = color("D2AD62")


def brush(fill, edge=None):
    result = unreal.SlateBrush()
    result.set_editor_property("draw_as", unreal.SlateBrushDrawType.ROUNDED_BOX)
    result.set_editor_property("tint_color", unreal.SlateColor(color(fill)))
    outline = result.get_editor_property("outline_settings")
    outline.set_editor_property("rounding_type", unreal.SlateBrushRoundingType.FIXED_RADIUS)
    outline.set_editor_property("corner_radii", unreal.Vector4(4, 4, 4, 4))
    outline.set_editor_property("color", unreal.SlateColor(color(edge or fill)))
    outline.set_editor_property("width", 1.0 if edge else 0.0)
    result.set_editor_property("outline_settings", outline)
    return result


bp = unreal.load_asset(ROOT + "/" + NAME) if unreal.EditorAssetLibrary.does_asset_exist(ROOT + "/" + NAME) else None
if bp is None:
    bp = UMG.call_method("CreateWidgetBlueprint", args=(ROOT, NAME, unreal.UserWidget.static_class()))
assert bp, NAME
for graph in BP.list_graphs(bp):
    for item in BP.find_nodes(graph):
        if item.get_class().get_name() not in ("K2Node_FunctionEntry", "K2Node_FunctionResult"):
            BP.delete_node(item)
for item in UMG.call_method("GetWidgets", args=(bp,)).widgets:
    if not item.parent:
        UMG.call_method("RemoveWidget", args=(bp, item.widget))


def add(kind, name, parent=None, variable=False):
    item = UMG.call_method("AddWidget", args=(bp, kind.static_class(), name, parent, -1))
    assert item.widget, name
    if variable:
        UMG.call_method("ToggleWidgetAsVariable", args=(bp, item.widget, True))
    return item.widget, item.widget.slot


root, _ = add(unreal.CanvasPanel, "Root")
root.set_visibility(unreal.SlateVisibility.SELF_HIT_TEST_INVISIBLE)
button, slot = add(unreal.Button, "SpawnButton", root, True)
# Directly below Remote Campfire's toggle (16, -22, 44 x 44, left middle).
slot.set_anchors(unreal.Anchors(unreal.Vector2D(0, 0.5), unreal.Vector2D(0, 0.5)))
slot.set_offsets(unreal.Margin(16, 30, 44, 44))
style = button.get_editor_property("widget_style")
for field, fill in (("normal", "343B3C"), ("hovered", "414A4A"), ("pressed", "202526"), ("disabled", "292E2E")):
    style.set_editor_property(field, brush(fill, "59605B"))
style.set_editor_property("normal_padding", unreal.Margin(0))
style.set_editor_property("pressed_padding", unreal.Margin(0))
button.set_editor_property("widget_style", style)
button.set_editor_property("is_focusable", False)
button.set_tool_tip_text(LABEL)
icon, slot = add(unreal.Image, "WhiskerIcon", button)
texture = unreal.load_asset("/Game/Assets/Icons/icons8-cat-head-96")
assert texture, "Native cat-head icon unavailable"
icon.set_brush_from_texture(texture, False)
icon.set_desired_size_override(unreal.Vector2D(32, 32))
icon.set_color_and_opacity(GOLD)
icon.set_visibility(unreal.SlateVisibility.HIT_TEST_INVISIBLE)
slot.set_padding(unreal.Margin(6, 6, 6, 6))
slot.set_horizontal_alignment(unreal.HorizontalAlignment.H_ALIGN_CENTER)
slot.set_vertical_alignment(unreal.VerticalAlignment.V_ALIGN_CENTER)

functions = {"HasObject": [("Object", unreal.Object.static_class())], "SetLabel": [("Label", "string")],
             "ApplyGameplayVisibility": [("Visible", "bool")], "SpawnClicked": []}
existing = set(BP.list_variables(bp))
if "GameplayVisible" not in existing:
    BP.add_variable(bp, "GameplayVisible", "bool")
if "Host" not in existing:
    BP.add_object_variable(bp, "Host", HOST)
old = {str(graph.get_name()) for graph in BP.list_graphs(bp)}
graphs = {}
for name, inputs in functions.items():
    graph = BP.get_graph(bp, name) if name in old else BP.add_function_graph(bp, name)
    graphs[name] = graph
    if name not in old:
        for param, kind in inputs:
            if isinstance(kind, str):
                BP.add_function_param(graph, param, kind, True)
            else:
                BP.add_object_function_param(graph, param, kind, True)
        BP.add_function_param(graph, "Result", "bool", False)
BP.compile_blueprint(bp)
context = graphs["SpawnClicked"]
nodes = list(dict.fromkeys(BP.find_node_types(context, "", [])))
normalize = lambda value: re.sub("[^a-z0-9]", "", str(value).lower())


def native(method, owner=None):
    candidates = [item for item in nodes if normalize(item.rsplit("|", 1)[-1].split("(", 1)[0]) == normalize(method)]
    if owner and len(candidates) > 1:
        candidates = [item for item in candidates if any(
            normalize(pin.type_id) == normalize(owner) + "objectreference"
            for pin in BP.get_node_type_pins(context, item).input_pins if pin.name in ("self", "Target"))]
        preferred = [item for item in candidates if not item.startswith("Class|")]
        candidates = preferred or candidates
    assert len(candidates) == 1, (method, owner, candidates)
    return candidates[0]


def scalar(method, owner, target, value):
    kind = native(method, owner)
    args = [pin.name for pin in BP.get_node_type_pins(context, kind).input_pins if pin.name not in ("self", "Target", "execute")]
    assert len(args) == 1, (method, args)
    return f"({kind} :self {target} :{args[0]} {value})"


getters = {item.rsplit("|Get", 1)[1]: item for item in nodes if item.startswith("Variables|") and "|Get" in item}
get = lambda name: "(" + getters.get(name, "Variables|Default|Get" + name) + ")"
to_text = next(item for item in nodes if item.endswith("|ToText(String)"))
code = {
    "HasObject": '(fn HasObject (Object) (Utilities|IsValid Object (:"Is Valid" (return true)) (:"Is Not Valid" (return false))))',
    "SetLabel": f"(fn SetLabel (Label) {scalar('SetToolTipText', 'Widget', get('SpawnButton'), f'({to_text} Label)')} (return true))",
    "ApplyGameplayVisibility": f'''(fn ApplyGameplayVisibility (Visible)
        (if (== Visible {get('GameplayVisible')}) (return true))
        (Variables|Default|SetGameplayVisible Visible)
        (if Visible {scalar('SetVisibility', 'Widget', 'self', '"SelfHitTestInvisible"')} (return true))
        {scalar('SetVisibility', 'Widget', 'self', '"Collapsed"')}
        (return true))''',
    "SpawnClicked": f'''(fn SpawnClicked ()
        (if (not (CallFunction|HasObject :Object {get('Host')})) (return false))
        (bind spawned ({native('SpawnOne', 'BPMapLoad')} :self {get('Host')})) (return spawned))''',
}
with toolset_registry.tool_raising_exceptions():
    for name, source in code.items():
        blueprint_dsl.parse(source)
        unreal.log("RANDOMWHISKER_UI_WRITE " + name)
        BP.write_graph_dsl(graphs[name], source)
    BP.compile_blueprint(bp, warnings_as_errors=True)
    event_graph = BP.get_graph(bp, "EventGraph")
    for item in BP.find_nodes(event_graph):
        BP.delete_node(item)
    before = set(str(item.get_path_name()) for item in BP.find_nodes(event_graph))
    assert UMG.call_method("BindToEventProperty", args=(bp, "OnClicked", "SpawnButton", unreal.Button.static_class()))
    event = next(item for item in BP.find_nodes(event_graph) if str(item.get_path_name()) not in before)
    target = BP.create_node(event_graph, "CallFunction|SpawnClicked", unreal.IntPoint(400, 0))
    source_info, target_info = BP.get_node_infos([event, target])
    BP.connect_pins(next(pin.pin_id for pin in source_info.output_pins if pin.name == "then"),
                    next(pin.pin_id for pin in target_info.input_pins if pin.name == "execute"))
    BP.compile_blueprint(bp, warnings_as_errors=True)
    cdo = unreal.get_default_object(bp.generated_class())
    cdo.set_editor_property("GameplayVisible", False, notify_mode=unreal.PropertyAccessChangeNotifyMode.NEVER)
    cdo.set_editor_property("visibility", unreal.SlateVisibility.COLLAPSED)
    assert unreal.EditorAssetLibrary.save_loaded_asset(bp)
unreal.log("RANDOMWHISKER_UI_GENERATED")
