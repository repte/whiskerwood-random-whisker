"""Check the public Blueprint boundary without executing the spawn."""
import re

import unreal
from editor_toolset.toolsets.blueprint import BlueprintTools as BP


ROOT = "/Game/Mods/RandomWhisker"
BRIDGE = "RwSpawnAtDock"
normalize = lambda value: re.sub("[^a-z0-9]", "", str(value).lower())
for name in ("BP_MapLoad", "WBP_RandomWhisker"):
    asset = unreal.load_asset(ROOT + "/" + name)
    assert isinstance(asset, unreal.Blueprint) and asset.generated_class(), ("Compiled asset missing", name)
    graphs = {str(graph.get_name()): graph for graph in BP.list_graphs(asset)}
    calls = {}
    for graph_name, graph in graphs.items():
        if graph_name == BRIDGE:
            continue  # The authoring helper verifies its bytecode when generating it.
        calls[graph_name] = [normalize(info.type_id.rsplit("|", 1)[-1].split("(", 1)[0])
                             for info in BP.get_node_infos(BP.find_nodes(graph))]
        forbidden = {"log", "logmessage", "printstring", "printtext", "executeconsolecommand"} & set(calls[graph_name])
        assert not forbidden, ("Diagnostics or console calls remain", name, graph_name, forbidden)
    if name == "BP_MapLoad":
        assert BRIDGE in graphs, "Native spawn bridge missing"
        required = {
            "SpawnOne": {"ready", normalize(BRIDGE), "getrealtimeseconds", "setlastspawn"},
            "Pump": {"ready", "createpanel", "syncpanelvisibility", "refreshlanguage"},
            "Ready": {"currentinitphase", "getarcosys", "islive"},
        }
        for graph_name, needed in required.items():
            missing = needed - set(calls.get(graph_name, []))
            assert not missing, ("Required call missing", graph_name, missing, calls.get(graph_name))
        for graph_name, graph_calls in calls.items():
            if graph_name != "SpawnOne":
                assert normalize(BRIDGE) not in graph_calls, ("Spawn reachable outside SpawnOne", graph_name)
    else:
        assert "spawnone" in calls.get("SpawnClicked", []), "Button does not call SpawnOne"
        assert all("spawnone" not in c for g, c in calls.items() if g != "SpawnClicked"), "Unexpected spawn call"
    unreal.log("RANDOMWHISKER_PUBLIC_ASSET_PASS " + name)
unreal.log("RANDOMWHISKER_PUBLIC_TESTS_PASS: spawn only via button; no diagnostics")
