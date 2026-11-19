#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "CivicFactionSubsystem.generated.h"

class UDataLayerAsset;

UENUM(BlueprintType)
enum class ECivicFaction : uint8
{
    AlbanicoAssociation UMETA(DisplayName = "The Albanico Association"),
    ThePod UMETA(DisplayName = "The YIMBY Cult of The Pod"),
    CargoBikeMilitia UMETA(DisplayName = "Radical Transit & Cargo-Bike Militia"),
    AsphaltCoalition UMETA(DisplayName = "Asphalt & Truck-Nutz Coalition"),
    LocalIndependents UMETA(DisplayName = "Small Local Independents"),
    CorporateCapital UMETA(DisplayName = "Outside Corporate Capital"),
    UrbanCore UMETA(DisplayName = "Urban Core Focus"),
    CountyAnnexation UMETA(DisplayName = "County Annexation"),
    MunicipalCommission UMETA(DisplayName = "Municipal Red-Tape & Blue-Ribbon Commission")
};

UENUM(BlueprintType)
enum class ECivicLayerTrigger : uint8
{
    FactionFavored,
    PermitsAvailable,
    EnforcementActive
};

UENUM(BlueprintType)
enum class ECivicLayerState : uint8
{
    Unloaded,
    Loaded,
    Activated
};

USTRUCT(BlueprintType)
struct RVACIVIC_API FCivicLayerRule
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Civic")
    TObjectPtr<UDataLayerAsset> Layer = nullptr;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Civic")
    ECivicLayerTrigger Trigger = ECivicLayerTrigger::FactionFavored;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Civic")
    ECivicFaction Faction = ECivicFaction::AlbanicoAssociation;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Civic", meta = (ClampMin = "1", ClampMax = "100"))
    int32 ReputationThreshold = 25;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Civic")
    ECivicLayerState ActiveState = ECivicLayerState::Activated;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Civic")
    ECivicLayerState InactiveState = ECivicLayerState::Unloaded;
};

USTRUCT(BlueprintType)
struct RVACIVIC_API FCivicCityState
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadOnly, Category = "Civic")
    int32 TaxRateBasisPoints = 425;

    UPROPERTY(BlueprintReadOnly, Category = "Civic")
    int32 AdministrativeShareBasisPoints = 9500;

    UPROPERTY(BlueprintReadOnly, Category = "Civic")
    int32 ResidentMorale = 100;

    UPROPERTY(BlueprintReadOnly, Category = "Civic")
    int32 LocalBusinessVitality = 100;

    UPROPERTY(BlueprintReadOnly, Category = "Civic")
    int32 RedTapeHeat = 0;

    UPROPERTY(BlueprintReadOnly, Category = "Civic")
    bool bPermitsAvailable = false;
};

USTRUCT(BlueprintType)
struct RVACIVIC_API FCivicFiscalPeriod
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadOnly, Category = "Civic")
    int64 TaxReceivedCents = 0;

    UPROPERTY(BlueprintReadOnly, Category = "Civic")
    int64 AdministrationCents = 0;

    UPROPERTY(BlueprintReadOnly, Category = "Civic")
    int64 PublicWorksCents = 0;
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FCivicReputationChanged, ECivicFaction, Faction, int32, Reputation);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FCivicCityChanged, const FCivicCityState&, CityState);

UCLASS(BlueprintType)
class RVACIVIC_API UCivicFactionSubsystem final : public UWorldSubsystem
{
    GENERATED_BODY()

public:
    UPROPERTY(BlueprintAssignable, Category = "Civic|Events")
    FCivicReputationChanged OnReputationChanged;

    UPROPERTY(BlueprintAssignable, Category = "Civic|Events")
    FCivicCityChanged OnCityStateChanged;

    UFUNCTION(BlueprintPure, Category = "Civic|Faction")
    int32 GetReputation(ECivicFaction Faction) const;

    UFUNCTION(BlueprintCallable, Category = "Civic|Faction")
    bool ChangeReputation(ECivicFaction Faction, int32 Delta);

    UFUNCTION(BlueprintPure, Category = "Civic|City")
    FCivicCityState GetCityState() const { return CityState; }

    UFUNCTION(BlueprintCallable, Category = "Civic|City")
    bool SetFiscalPolicy(int32 TaxRateBasisPoints, int32 AdministrativeShareBasisPoints);

    UFUNCTION(BlueprintPure, Category = "Civic|City")
    FCivicFiscalPeriod EstimateFiscalPeriod(int64 TaxBaseCents) const;

    UFUNCTION(BlueprintCallable, Category = "Civic|City")
    bool AddRedTapeHeat(int32 Delta);

    UFUNCTION(BlueprintCallable, Category = "Civic|Streaming")
    bool ConfigureLayerOverrides(const TArray<FCivicLayerRule>& Rules);

    UFUNCTION(BlueprintCallable, Category = "Civic|Streaming")
    bool RefreshLayerOverrides();

    virtual void OnWorldBeginPlay(UWorld& InWorld) override;

protected:
    virtual bool DoesSupportWorldType(EWorldType::Type WorldType) const override;

private:
    UPROPERTY(Transient)
    TArray<FCivicLayerRule> LayerOverrides;

    UPROPERTY(Transient)
    TMap<ECivicFaction, int32> Reputation;

    UPROPERTY(Transient)
    FCivicCityState CityState;

    bool CanMutate() const;
    bool RuleMatches(const FCivicLayerRule& Rule) const;
    void CommitCityState();
};
