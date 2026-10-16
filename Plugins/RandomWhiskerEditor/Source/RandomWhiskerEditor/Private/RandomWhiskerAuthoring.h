#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "RandomWhiskerAuthoring.generated.h"

class UBlueprint;

UCLASS()
class URandomWhiskerAuthoring final : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:
    // Marks the Suzie editor stub of Arco_SpawnAgentsAtDock as Blueprint-callable for this editor session.
    UFUNCTION(BlueprintCallable, Category = "Random Whisker Authoring")
    static FString EnableAuthoring();

    // Adds RwSpawnAtDock(Controller) to the Blueprint. Compiles only; never executes the game call.
    UFUNCTION(BlueprintCallable, Category = "Random Whisker Authoring")
    static FString AddRuntimeBridge(UBlueprint* Blueprint);
};
