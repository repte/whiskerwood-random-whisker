using UnrealBuildTool;

public class RandomWhiskerEditor : ModuleRules
{
    public RandomWhiskerEditor(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PrivateDependencyModuleNames.AddRange(new[] {
            "Core", "CoreUObject", "Engine", "UnrealEd", "BlueprintGraph",
            "KismetCompiler", "ScriptDisassembler", "Json"
        });
    }
}
