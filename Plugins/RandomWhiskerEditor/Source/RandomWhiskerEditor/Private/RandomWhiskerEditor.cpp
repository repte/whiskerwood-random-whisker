#include "RandomWhiskerAuthoring.h"
#include "Modules/ModuleManager.h"

class FRandomWhiskerEditorModule final : public IModuleInterface
{
public:
    virtual void StartupModule() override
    {
        UE_LOG(LogTemp, Display, TEXT("RANDOMWHISKER_AUTHORING_ACCESS %s"), *URandomWhiskerAuthoring::EnableAuthoring());
    }
};

IMPLEMENT_MODULE(FRandomWhiskerEditorModule, RandomWhiskerEditor)
