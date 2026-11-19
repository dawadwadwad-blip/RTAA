#if WITH_DEV_AUTOMATION_TESTS

#include "ChurchHillSliceDirector.h"

#include "Components/BoxComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/EngineBaseTypes.h"
#include "Engine/World.h"
#include "GameFramework/GameModeBase.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/SpectatorPawn.h"
#include "GameFramework/WorldSettings.h"
#include "Misc/AutomationTest.h"
#include "NightShiftWorkOrder.h"
#include "Tests/AutomationCommon.h"
#include "UObject/UObjectGlobals.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FChurchHillSliceNativeFlow, "RVA.Graybox.ChurchHillSliceNativeFlow",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FChurchHillSliceNativeFlow::RunTest(const FString&)
{
    const auto RunRoute = [this](bool bHardRoute)
    {
        FTestWorldWrapper TestWorld;
        if (!TestTrue(TEXT("Create the temporary game world"), TestWorld.CreateTestWorld(EWorldType::Game)))
        {
            TestWorld.ForwardErrorMessages(this);
            return;
        }
        UWorld* World = TestWorld.GetTestWorld();
        World->GetWorldSettings()->DefaultGameMode = AGameModeBase::StaticClass();
        if (!TestTrue(TEXT("Set the base game mode"), World->SetGameMode(FURL())))
        {
            return;
        }

        FActorSpawnParameters Spawn;
        Spawn.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
        auto* Night = World->SpawnActor<ANightShiftWorkOrder>(FVector::ZeroVector, FRotator::ZeroRotator, Spawn);
        auto* Hill = World->SpawnActor<AHillClimbGraybox>(FVector(7000, 0, 0), FRotator::ZeroRotator, Spawn);
        auto* Survey = World->SpawnActor<ASurveyStakesGraybox>(FVector(13000, 0, 0), FRotator::ZeroRotator, Spawn);
        auto* Director = World->SpawnActor<AChurchHillSliceDirector>(FVector::ZeroVector, FRotator::ZeroRotator, Spawn);
        auto* Controller = World->SpawnActor<APlayerController>(FVector::ZeroVector, FRotator::ZeroRotator, Spawn);
        auto* Driver = World->SpawnActor<ASpectatorPawn>(FVector(0, 0, 90), FRotator::ZeroRotator, Spawn);
        auto* Ledger = World->GetSubsystem<UCivicWorkOrderSubsystem>();
        if (!TestNotNull(TEXT("Night Shift"), Night) || !TestNotNull(TEXT("Hill Climb"), Hill)
            || !TestNotNull(TEXT("Survey Stakes"), Survey) || !TestNotNull(TEXT("Slice director"), Director)
            || !TestNotNull(TEXT("Controller"), Controller) || !TestNotNull(TEXT("Driver"), Driver)
            || !TestNotNull(TEXT("Shared Work Order ledger"), Ledger))
        {
            return;
        }

        Night->bBindTestKeys = false;
        Hill->bBindTestKey = false;
        Survey->bBindTestKey = false;
        Survey->HardTimeLimitSeconds = 5.0f;
        Director->NightShift = Night;
        Director->HillClimb = Hill;
        Director->SurveyStakes = Survey;
        Director->PlaytestTruckClass = ASpectatorPawn::StaticClass();
        Director->NightOutcome.HouseholdsHelped = 1;
        Director->HillGentleOutcome.HouseholdsHelped = 1;
        Director->HillDirectOutcome.HouseholdsHelped = 1;
        Director->SurveyKindOutcome.HouseholdsHelped = 2;
        Director->SurveyHardOutcome.HouseholdsHelped = 2;
        Director->SurveyHardOutcome.HouseholdsHarmed = 1;
        Director->SurveyHardOutcome.Collateral = 1;
        Director->SurveyHardOutcome.DistrictStrainDelta = 1;

        if (!TestTrue(TEXT("Start play in the test world"), TestWorld.BeginPlayInTestWorld()))
        {
            TestWorld.ForwardErrorMessages(this);
            return;
        }
        Controller->Possess(Driver);
        Director->Tick(0.2f);
        if (!TestTrue(TEXT("Director identifies the possessed truck"), Controller->GetPawn() == Driver
                && Driver->ActorHasTag(Night->TruckTag) && Driver->ActorHasTag(Hill->TruckTag)))
        {
            return;
        }

        const auto Move = [this, Driver](AActor& Job, const TCHAR* Name, double Along = 0.0)
        {
            const auto* Zone = FindObjectFast<UBoxComponent>(&Job, FName(Name));
            if (!TestNotNull(Name, Zone))
            {
                return false;
            }
            Driver->SetActorLocation(Zone->GetComponentTransform().TransformPosition(
                FVector(Zone->GetUnscaledBoxExtent().X * Along, 0, 0)), false, nullptr, ETeleportType::TeleportPhysics);
            return true;
        };

        const auto CheckLedger = [this, Director, Ledger](const TCHAR* ActiveId, int32 Completed)
        {
            const FName Expected = ActiveId ? FName(ActiveId) : NAME_None;
            TestEqual(TEXT("Director current job"), Director->GetCurrentMissionId(), Expected);
            TestEqual(TEXT("Ledger has an active job"), Ledger->HasActiveWorkOrder(), ActiveId != nullptr);
            TestEqual(TEXT("Active ledger job"), Ledger->GetActiveWorkOrder().MissionId, Expected);
            TestEqual(TEXT("Work orders completed"), Ledger->GetCampaignProgress().CompletedWorkOrders, Completed);
        };

        CheckLedger(TEXT("M01"), 0);
        TestTrue(TEXT("Move to Hill pickup before Night Shift"), Move(*Hill, TEXT("CornicePickup")));
        TestFalse(TEXT("Hill Climb is locked at the start"), Hill->PerformObjective(Driver));
        TestTrue(TEXT("Move to Survey brief before Night Shift"), Move(*Survey, TEXT("ReviewBoardBrief")));
        TestFalse(TEXT("Survey Stakes is locked at the start"), Survey->PerformObjective(Driver));
        TestTrue(TEXT("Move to the yard"), Move(*Night, TEXT("Yard")));
        TestTrue(TEXT("Acknowledge the order"), Night->PerformObjective(Driver));
        TestTrue(TEXT("Begin striping"), Night->PerformObjective(Driver));

        for (const TCHAR* Segment : {TEXT("SegmentA"), TEXT("SegmentB")})
        {
            TestTrue(TEXT("Move to start of stripe"), Move(*Night, Segment, -0.9));
            Night->Tick(0.05f);
            TestTrue(TEXT("Arm stripe"), Night->PerformObjective(Driver));
            TestTrue(TEXT("Move to end of stripe"), Move(*Night, Segment, 0.9));
            Night->Tick(0.05f);
            if (FCString::Strcmp(Segment, TEXT("SegmentA")) == 0)
            {
                TestTrue(TEXT("Retry after first stripe"), Night->RetryCheckpoint(Driver));
                CheckLedger(TEXT("M01"), 0);
            }
        }
        CheckLedger(TEXT("M01"), 0);
        TestTrue(TEXT("Reach the selected exit"), Move(*Night, bHardRoute ? TEXT("RecoveryExit") : TEXT("DetourExit")));
        Night->Tick(0.05f);
        TestTrue(TEXT("Return to the yard"), Move(*Night, TEXT("Yard")));
        TestTrue(TEXT("Debrief files Night Shift"), Night->PerformObjective(Driver));
        FNightShiftEvidence Evidence;
        TestTrue(TEXT("Night Shift records the selected exit"), Night->GetEvidence(Evidence)
            && Evidence.ExitTaken == (bHardRoute ? ENightShiftExit::Recovery : ENightShiftExit::Detour));
        TestFalse(TEXT("Debrief cannot file twice"), Night->PerformObjective(Driver));
        CheckLedger(TEXT("M13"), 1);

        TestTrue(TEXT("Move to cornice"), Move(*Hill, TEXT("CornicePickup")));
        TestTrue(TEXT("Load cornice"), Hill->PerformObjective(Driver));
        TestTrue(TEXT("Move to selected grade"), Move(*Hill, bHardRoute ? TEXT("DirectHill") : TEXT("GentleHill")));
        TestTrue(TEXT("Accept the selected grade"), Hill->PerformObjective(Driver));
        TestTrue(TEXT("Hill Climb records the selected grade"), Hill->GetRoute()
            == (bHardRoute ? EChurchHillRoute::Direct : EChurchHillRoute::Gentle));
        TestTrue(TEXT("Reach final grade warning"), Move(*Hill, TEXT("FinalGradeWarning")));
        Hill->Tick(0.1f);
        TestTrue(TEXT("Move to pull-off"), Move(*Hill, TEXT("StrapPullOff")));
        TestTrue(TEXT("Secure the cornice"), Hill->PerformObjective(Driver));
        TestTrue(TEXT("Move to upper delivery"), Move(*Hill, TEXT("CorniceDelivery")));
        TestTrue(TEXT("Deliver the cornice"), Hill->PerformObjective(Driver));
        TestFalse(TEXT("Delivery cannot file twice"), Hill->PerformObjective(Driver));
        CheckLedger(TEXT("M04"), 2);

        const auto* Stake = FindObjectFast<UStaticMeshComponent>(Survey, FName(TEXT("SurveyStakeA")));
        const auto* Barrier = FindObjectFast<UBoxComponent>(Survey, FName(TEXT("HardLoadingBarrier")));
        if (!TestNotNull(TEXT("Survey stake A"), Stake) || !TestNotNull(TEXT("Loading barrier"), Barrier))
        {
            return;
        }
        const FVector StakeStart = Stake->GetRelativeLocation();
        const TCHAR* Brief = bHardRoute ? TEXT("MortarCircleBrief") : TEXT("ReviewBoardBrief");
        if (bHardRoute)
        {
            TestTrue(TEXT("Move to the first Hard briefing"), Move(*Survey, Brief));
            TestTrue(TEXT("Start the first Hard attempt"), Survey->PerformObjective(Driver));
            TestTrue(TEXT("Move to the first stake"), Move(*Survey, TEXT("OccupiedStoopA")));
            TestTrue(TEXT("Move the first stake"), Survey->PerformObjective(Driver));
            TestFalse(TEXT("Hard attempt changes the stake"), Stake->GetRelativeLocation().Equals(StakeStart));
            Survey->Tick(5.1f);
            TestTrue(TEXT("Expiry restores the stake"), Stake->GetRelativeLocation().Equals(StakeStart));
            TestTrue(TEXT("Expiry leaves loading open"), Barrier->GetCollisionEnabled() == ECollisionEnabled::NoCollision);
            CheckLedger(TEXT("M04"), 2);
        }

        TestTrue(TEXT("Move to Survey briefing"), Move(*Survey, Brief));
        TestTrue(TEXT("Start Survey Stakes"), Survey->PerformObjective(Driver));
        TestTrue(TEXT("Move to second site"), Move(*Survey, TEXT("OccupiedStoopB")));
        TestTrue(TEXT("Mark second site"), Survey->PerformObjective(Driver));
        CheckLedger(TEXT("M04"), 2);
        TestTrue(TEXT("Move to first site"), Move(*Survey, TEXT("OccupiedStoopA")));
        TestTrue(TEXT("Mark first site and file Survey Stakes"), Survey->PerformObjective(Driver));
        TestFalse(TEXT("Survey Stakes cannot file twice"), Survey->PerformObjective(Driver));
        TestTrue(TEXT("Loading collision matches the Survey method"), Barrier->GetCollisionEnabled()
            == (bHardRoute ? ECollisionEnabled::QueryAndPhysics : ECollisionEnabled::NoCollision));
        CheckLedger(nullptr, 3);
        for (const TCHAR* Id : {TEXT("M01"), TEXT("M13"), TEXT("M04")})
        {
            TestTrue(Id, Ledger->WasWorkOrderCompleted(FName(Id)));
        }

        const FCivicCampaignProgress Progress = Ledger->GetCampaignProgress();
        TestEqual(TEXT("Households helped"), Progress.HouseholdsHelped, int64(4));
        TestEqual(TEXT("Households harmed"), Progress.HouseholdsHarmed, int64(bHardRoute ? 1 : 0));
        TestEqual(TEXT("Collateral"), Progress.Collateral, int64(bHardRoute ? 1 : 0));
        TestEqual(TEXT("Church Hill Strain"), Ledger->GetDistrictStrain(FName(TEXT("ChurchHill"))), bHardRoute ? 1 : 0);
    };

    RunRoute(false);
    RunRoute(true);
    return !HasAnyErrors();
}

#endif
