#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "StandingCommitteeProgress.h"
#include "StandingCommitteeFavor.generated.h"

class ACharacter;
class UChildActorComponent;
class UPrimitiveComponent;
class USceneComponent;
class USphereComponent;
class UTextRenderComponent;

UCLASS(NotBlueprintable)
class RVACIVIC_API AStandingCommitteeHandTruck final : public AActor
{
    GENERATED_BODY()

public:
    AStandingCommitteeHandTruck();
};

UENUM(BlueprintType)
enum class EStandingCommitteeFavorStage : uint8
{
    Available,
    Borrowed,
    Returned
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FStandingFavorChanged, EStandingCommitteeFavorStage, NewStage,
    const FText&, Message);

UCLASS(BlueprintType)
class RVACIVIC_API AStandingCommitteeFavor final : public AActor
{
    GENERATED_BODY()

public:
    AStandingCommitteeFavor();
    virtual void OnConstruction(const FTransform& Transform) override;

    UPROPERTY(EditInstanceOnly, Category = "Standing Committee")
    TObjectPtr<AActor> CourtyardGate = nullptr;

    UPROPERTY(BlueprintAssignable, Category = "Standing Committee")
    FStandingFavorChanged OnFavorChanged;

    UFUNCTION(BlueprintPure, Category = "Standing Committee")
    EStandingCommitteeFavorStage GetStage() const;

    UFUNCTION(BlueprintPure, Category = "Standing Committee")
    FText GetObjective() const;

protected:
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

private:
    UPROPERTY(VisibleAnywhere, Category = "Standing Committee|Placement")
    TObjectPtr<USceneComponent> PickupSite;

    UPROPERTY(VisibleAnywhere, Category = "Standing Committee|Placement")
    TObjectPtr<USceneComponent> ReturnSite;

    UPROPERTY(VisibleAnywhere, Category = "Standing Committee|Placement")
    TObjectPtr<UChildActorComponent> PickupSkeleton;

    UPROPERTY(VisibleAnywhere, Category = "Standing Committee|Placement")
    TObjectPtr<UChildActorComponent> ReturnSkeleton;

    UPROPERTY(VisibleAnywhere, Category = "Standing Committee|Placement")
    TObjectPtr<USphereComponent> PickupZone;

    UPROPERTY(VisibleAnywhere, Category = "Standing Committee|Placement")
    TObjectPtr<USphereComponent> ReturnZone;

    UPROPERTY(VisibleAnywhere, Category = "Standing Committee|Placement")
    TObjectPtr<UTextRenderComponent> PickupPrompt;

    UPROPERTY(VisibleAnywhere, Category = "Standing Committee|Placement")
    TObjectPtr<UTextRenderComponent> ReturnPrompt;

    UPROPERTY(Transient)
    TObjectPtr<AStandingCommitteeHandTruck> HandTruck;

    TWeakObjectPtr<ACharacter> Borrower;
    RVA::StandingCommittee::FavorProgress Progress;

    void ApplySignals();
    void RefreshPrompts();
    void NotifyStage();
    void TryBorrow(ACharacter& Character);
    void TryReturn(ACharacter& Character);
    void ParkTruck(const USceneComponent& Site);

    UFUNCTION()
    void HandlePickupOverlap(UPrimitiveComponent* OverlappedComponent, AActor* OtherActor,
        UPrimitiveComponent* OtherComponent, int32 OtherBodyIndex, bool bFromSweep, const FHitResult& SweepResult);

    UFUNCTION()
    void HandleReturnOverlap(UPrimitiveComponent* OverlappedComponent, AActor* OtherActor,
        UPrimitiveComponent* OtherComponent, int32 OtherBodyIndex, bool bFromSweep, const FHitResult& SweepResult);

    UFUNCTION()
    void HandleBorrowerDestroyed(AActor* DestroyedActor);
};
