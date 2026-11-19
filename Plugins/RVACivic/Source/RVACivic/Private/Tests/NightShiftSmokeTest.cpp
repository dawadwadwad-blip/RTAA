#if WITH_DEV_AUTOMATION_TESTS

#include "NightShiftWorkOrder.h"

#include "Components/BoxComponent.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/SpectatorPawn.h"
#include "Misc/AutomationTest.h"
#include "Misc/ScopeExit.h"
#include "UObject/UObjectGlobals.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FNightShiftNativeFlow, "RVA.Graybox.NightShiftNativeFlow",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FNightShiftNativeFlow::RunTest(const FString&)
{
    UWorld* World = UWorld::CreateWorld(EWorldType::Game, false);
    if (!TestNotNull(TEXT("Transient game world"), World))
    {
        return false;
    }
    ON_SCOPE_EXIT { World->DestroyWorld(false); };

    FActorSpawnParameters Spawn;
    Spawn.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    auto* Order = World->SpawnActor<ANightShiftWorkOrder>(FVector::ZeroVector, FRotator::ZeroRotator, Spawn);
    auto* Controller = World->SpawnActor<APlayerController>(FVector::ZeroVector, FRotator::ZeroRotator, Spawn);
    auto* Driver = World->SpawnActor<ASpectatorPawn>(FVector(0, 0, 90), FRotator::ZeroRotator, Spawn);
    if (!TestNotNull(TEXT("Native work-order actor"), Order) || !TestNotNull(TEXT("Controller"), Controller)
        || !TestNotNull(TEXT("Steered smoke-test pawn"), Driver))
    {
        return false;
    }
    Order->bBindTestKeys = false;
    Driver->Tags.Add(Order->TruckTag);
    Controller->Possess(Driver);
    if (!TestTrue(TEXT("Possesses the smoke-test pawn"), Controller->GetPawn() == Driver))
    {
        return false;
    }

    auto* A = FindObjectFast<UBoxComponent>(Order, FName(TEXT("SegmentA")));
    auto* B = FindObjectFast<UBoxComponent>(Order, FName(TEXT("SegmentB")));
    auto* Yard = FindObjectFast<UBoxComponent>(Order, FName(TEXT("Yard")));
    auto* Exit = FindObjectFast<UBoxComponent>(Order, FName(TEXT("RecoveryExit")));
    auto* Barrier = FindObjectFast<UBoxComponent>(Order, FName(TEXT("MainExitBarrier")));
    if (!TestNotNull(TEXT("Stripe A"), A) || !TestNotNull(TEXT("Stripe B"), B) || !TestNotNull(TEXT("Yard"), Yard)
        || !TestNotNull(TEXT("Alternate exit"), Exit) || !TestNotNull(TEXT("Barrier"), Barrier))
    {
        return false;
    }
    const auto Drive = [&](const UBoxComponent& Zone, double Along)
    {
        Driver->SetActorLocation(Zone.GetComponentTransform().TransformPosition(
            FVector(Zone.GetUnscaledBoxExtent().X * Along, 0, 0)), false, nullptr, ETeleportType::TeleportPhysics);
        Order->Tick(0.05f);
    };

    Drive(*Yard, 0);
    TestTrue(TEXT("Brief from the yard"), Order->PerformObjective(Driver));
    TestTrue(TEXT("Board the tagged truck"), Order->PerformObjective(Driver));
    Drive(*A, 0);
    TestFalse(TEXT("Reject starting in the middle of a segment"), Order->PerformObjective(Driver));
    Drive(*A, -0.9);
    TestTrue(TEXT("Arm A from the entry end"), Order->PerformObjective(Driver));
    Drive(*A, 0.9);
    TestTrue(TEXT("Checkpoint retry after A"), Order->RetryCheckpoint(Driver));
    Drive(*A, -0.9);
    TestFalse(TEXT("Retry keeps A complete"), Order->PerformObjective(Driver));
    Drive(*B, -0.9);
    TestTrue(TEXT("Arm B"), Order->PerformObjective(Driver));
    Drive(*B, 0.9);
    TestTrue(TEXT("Both stripes close the main road"), Order->GetPhase() == ENightShiftPhase::Detour
        && Barrier->GetCollisionEnabled() == ECollisionEnabled::QueryAndPhysics);

    FNightShiftEvidence First;
    TestFalse(TEXT("Evidence remains unavailable before debrief"), Order->GetEvidence(First));
    Drive(*Yard, 0);
    TestFalse(TEXT("Yard cannot bypass the detour"), Order->PerformObjective(Driver));
    Drive(*Exit, 0.4);
    TestTrue(TEXT("Alternate exit clears the site"), Order->GetPhase() == ENightShiftPhase::ReturnToYard);
    Drive(*Yard, 0);
    TestTrue(TEXT("Debrief at the yard"), Order->PerformObjective(Driver));
    TestTrue(TEXT("Evidence records the alternate exit"), Order->GetEvidence(First)
        && First.ExitTaken == ENightShiftExit::Recovery && !First.LogEntry.IsNone() && !First.DispatchStub.IsNone());
    TestTrue(TEXT("Completed state retries"), Order->RetryCheckpoint(Driver));

    FNightShiftEvidence Again;
    TestTrue(TEXT("Retry keeps both records and the exit sample"), Order->GetEvidence(Again)
        && First.DispatchStub == Again.DispatchStub && First.LogEntry == Again.LogEntry
        && First.ExitLocation.Equals(Again.ExitLocation) && First.TruckExitSeconds == Again.TruckExitSeconds);
    TestFalse(TEXT("Debrief cannot complete twice"), Order->PerformObjective(Driver));
    return !HasAnyErrors();
}

#endif
