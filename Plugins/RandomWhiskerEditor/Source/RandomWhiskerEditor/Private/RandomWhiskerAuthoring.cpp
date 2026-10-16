#include "RandomWhiskerAuthoring.h"

#include "Dom/JsonObject.h"
#include "EdGraph/EdGraph.h"
#include "EdGraphSchema_K2.h"
#include "Engine/Blueprint.h"
#include "Engine/BlueprintGeneratedClass.h"
#include "K2Node_CallFunction.h"
#include "K2Node_FunctionEntry.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "KismetCompiler.h"
#include "Misc/OutputDevice.h"
#include "Modules/ModuleManager.h"
#include "ScriptDisassembler.h"
#include "Serialization/JsonSerializer.h"
#include "UObject/UnrealType.h"

namespace
{
    const TCHAR* BridgeName = TEXT("RwSpawnAtDock");

    struct FSpawnContract
    {
        UClass* Controller = nullptr;
        UFunction* Spawn = nullptr;
        UEnum* Education = nullptr;

        bool Resolve()
        {
            FModuleManager::LoadModuleChecked<IModuleInterface>(TEXT("Suzie"));
            Controller = FindObject<UClass>(nullptr, TEXT("/Script/ProjectArco.PlayerController_Play"));
            if (!Controller) return false;
            Spawn = Controller->FindFunctionByName(TEXT("Arco_SpawnAgentsAtDock"));
            if (!Spawn || Spawn->GetOuter() != Controller || Spawn->NumParms != 2) return false;
            FIntProperty* Count = FindFProperty<FIntProperty>(Spawn, TEXT("nAgents"));
            FEnumProperty* EducationProperty = FindFProperty<FEnumProperty>(Spawn, TEXT("education"));
            Education = EducationProperty ? EducationProperty->GetEnum() : nullptr;
            return Count && Education && Education->GetNameStringByValue(0) == TEXT("None");
        }

        void Enable() const
        {
            // Suzie editor stub only; the running game keeps its own native function.
            Spawn->FunctionFlags &= ~(FUNC_Private | FUNC_Protected);
            Spawn->FunctionFlags |= FUNC_Public | FUNC_BlueprintCallable;
        }
    };

    class FProbeOutput final : public FOutputDevice
    {
    public:
        FString Text;
        virtual void Serialize(const TCHAR* Message, ELogVerbosity::Type, const FName&) override
        {
            Text += Message;
            Text += TEXT("\n");
        }
    };

    FString Json(const TSharedRef<FJsonObject>& Report)
    {
        FString Result;
        FJsonSerializer::Serialize(Report, TJsonWriterFactory<>::Create(&Result));
        return Result;
    }
}

FString URandomWhiskerAuthoring::EnableAuthoring()
{
    const TSharedRef<FJsonObject> Report = MakeShared<FJsonObject>();
    FSpawnContract Contract;
    const bool bValid = Contract.Resolve();
    if (bValid) Contract.Enable();
    Report->SetBoolField(TEXT("success"), bValid);
    Report->SetStringField(TEXT("scope"), TEXT("Suzie editor-stub flags for this editor session only."));
    if (!bValid) Report->SetStringField(TEXT("error"), TEXT("Arco_SpawnAgentsAtDock contract changed; no flags altered."));
    return Json(Report);
}

FString URandomWhiskerAuthoring::AddRuntimeBridge(UBlueprint* Blueprint)
{
    const TSharedRef<FJsonObject> Report = MakeShared<FJsonObject>();
    Report->SetBoolField(TEXT("success"), false);
    Report->SetBoolField(TEXT("native_action_executed"), false);
    const auto Fail = [&Report](const FString& Message)
    {
        Report->SetStringField(TEXT("error"), Message);
        return Json(Report);
    };

    if (!IsValid(Blueprint)) return Fail(TEXT("A valid Blueprint is required."));
    FSpawnContract Contract;
    if (!Contract.Resolve()) return Fail(TEXT("Arco_SpawnAgentsAtDock contract changed."));
    Contract.Enable();
    for (UEdGraph* Existing : Blueprint->FunctionGraphs)
        if (Existing->GetFName() == FName(BridgeName)) return Fail(TEXT("Runtime bridge already exists; remove it first."));

    UEdGraph* Graph = FBlueprintEditorUtils::CreateNewGraph(
        Blueprint, FName(BridgeName), UEdGraph::StaticClass(), UEdGraphSchema_K2::StaticClass());
    FBlueprintEditorUtils::AddFunctionGraph<UClass>(Blueprint, Graph, true, nullptr);
    UK2Node_FunctionEntry* Entry = nullptr;
    for (UEdGraphNode* Node : Graph->Nodes)
        if ((Entry = Cast<UK2Node_FunctionEntry>(Node)) != nullptr) break;
    if (!Entry) return Fail(TEXT("Missing bridge function entry."));
    Entry->SetExtraFlags(FUNC_Public | FUNC_BlueprintCallable);

    FEdGraphPinType ControllerType;
    ControllerType.PinCategory = UEdGraphSchema_K2::PC_Object;
    ControllerType.PinSubCategoryObject = Contract.Controller;
    UEdGraphPin* ControllerInput = Entry->CreateUserDefinedPin(TEXT("Controller"), ControllerType, EGPD_Output);

    UK2Node_CallFunction* Call = NewObject<UK2Node_CallFunction>(Graph);
    Graph->AddNode(Call, false, false);
    Call->CreateNewGuid();
    Call->SetFromFunction(Contract.Spawn);
    Call->AllocateDefaultPins();

    const UEdGraphSchema* Schema = Graph->GetSchema();
    UEdGraphPin* CountPin = Call->FindPin(TEXT("nAgents"));
    UEdGraphPin* EducationPin = Call->FindPin(TEXT("education"));
    UEdGraphPin* SelfPin = Call->FindPin(UEdGraphSchema_K2::PN_Self);
    UEdGraphPin* ExecPin = Call->FindPin(UEdGraphSchema_K2::PN_Execute);
    UEdGraphPin* ThenPin = Entry->FindPin(UEdGraphSchema_K2::PN_Then);
    if (!CountPin || !EducationPin || !SelfPin || !ExecPin || !ThenPin) return Fail(TEXT("Native call pins are missing."));
    Schema->TrySetDefaultValue(*CountPin, TEXT("1"));
    Schema->TrySetDefaultValue(*EducationPin, Contract.Education->GetNameStringByValue(0));
    if (!Schema->TryCreateConnection(ThenPin, ExecPin) || !Schema->TryCreateConnection(ControllerInput, SelfPin))
        return Fail(TEXT("Cannot connect the native call."));

    FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);
    FCompilerResultsLog Results;
    FKismetEditorUtilities::CompileBlueprint(Blueprint, EBlueprintCompileOptions::SkipGarbageCollection, &Results);
    Report->SetNumberField(TEXT("compile_errors"), Results.NumErrors);
    Report->SetNumberField(TEXT("compile_warnings"), Results.NumWarnings);
    if (Results.NumErrors || !Blueprint->GeneratedClass || Blueprint->Status == BS_Error)
        return Fail(TEXT("Blueprint did not compile; see editor compiler log."));

    UFunction* Bridge = Blueprint->GeneratedClass->FindFunctionByName(FName(BridgeName));
    if (!Bridge || Bridge->NumParms != 1 || !FindFProperty<FObjectProperty>(Bridge, TEXT("Controller")))
        return Fail(TEXT("Compiled bridge signature differs from the contract."));
    FProbeOutput Output;
    FKismetBytecodeDisassembler Disassembler(Output);
    Disassembler.DisassembleStructure(Bridge);
    Report->SetStringField(TEXT("bridge_bytecode"), Output.Text);
    const bool bNativeCall = Output.Text.Contains(TEXT("Arco_SpawnAgentsAtDock"));
    bool bEditorReference = false;
    for (const TObjectPtr<UObject>& Reference : Bridge->ScriptAndPropertyObjectReferences)
        if (Reference && Reference->GetPathName().StartsWith(TEXT("/Script/RandomWhiskerEditor."))) bEditorReference = true;
    Report->SetBoolField(TEXT("native_call_present"), bNativeCall);
    Report->SetBoolField(TEXT("editor_plugin_runtime_reference"), bEditorReference);
    Report->SetBoolField(TEXT("success"), bNativeCall && !bEditorReference);
    return Json(Report);
}
