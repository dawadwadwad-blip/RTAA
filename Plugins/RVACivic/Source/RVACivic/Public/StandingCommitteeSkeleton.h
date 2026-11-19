#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "StandingCommitteeSkeleton.generated.h"

class UInstancedStaticMeshComponent;

UENUM(BlueprintType)
enum class EStandingCommitteeSignal : uint8
{
    Bare,
    SafetyVest,
    MeetingChair
};

UCLASS(BlueprintType)
class RVACIVIC_API AStandingCommitteeSkeleton final : public AActor
{
    GENERATED_BODY()

public:
    AStandingCommitteeSkeleton();
    virtual void OnConstruction(const FTransform& Transform) override;

    UFUNCTION(BlueprintCallable, Category = "Standing Committee")
    void SetSignal(EStandingCommitteeSignal NewSignal);

    UFUNCTION(BlueprintPure, Category = "Standing Committee")
    EStandingCommitteeSignal GetSignal() const { return Signal; }

protected:
    virtual void BeginPlay() override;

private:
    UPROPERTY(EditAnywhere, Category = "Standing Committee")
    EStandingCommitteeSignal Signal = EStandingCommitteeSignal::Bare;

    UPROPERTY(VisibleAnywhere, Category = "Standing Committee")
    TObjectPtr<UInstancedStaticMeshComponent> Bones;

    UPROPERTY(VisibleAnywhere, Category = "Standing Committee")
    TObjectPtr<UInstancedStaticMeshComponent> RoundedBones;

    UPROPERTY(VisibleAnywhere, Category = "Standing Committee")
    TObjectPtr<UInstancedStaticMeshComponent> EyeSockets;

    UPROPERTY(VisibleAnywhere, Category = "Standing Committee")
    TObjectPtr<UInstancedStaticMeshComponent> Fabric;

    UPROPERTY(VisibleAnywhere, Category = "Standing Committee")
    TObjectPtr<UInstancedStaticMeshComponent> Metal;

    void Rebuild();
};
