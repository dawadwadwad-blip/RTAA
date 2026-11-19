#pragma once

#include <algorithm>
#include <cstdint>

namespace RVA::CivicPolicy
{
inline constexpr int BasisPoints = 10000;
inline constexpr int BaselineTax = 425;
inline constexpr int MaximumTax = 2000;
inline constexpr int PermitTax = 450;
inline constexpr int EnforcementThreshold = 60;

constexpr int BoundedReputation(int Previous, int Change)
{
    return std::clamp(std::clamp(Previous, -100, 100) + std::clamp(Change, -100, 100), -100, 100);
}

constexpr int RivalResponse(int EffectiveChange)
{
    return -EffectiveChange / 2;
}

constexpr std::int64_t Allocate(std::int64_t Amount, int Rate)
{
    const auto PositiveAmount = std::max<std::int64_t>(0, Amount);
    const auto BoundedRate = std::clamp(Rate, 0, BasisPoints);
    return (PositiveAmount / BasisPoints) * BoundedRate + ((PositiveAmount % BasisPoints) * BoundedRate) / BasisPoints;
}

struct Outcomes
{
    int ResidentMorale;
    int BusinessVitality;
    bool PermitsAvailable;
};

constexpr Outcomes Evaluate(int TaxRate, int AdminShare, int Heat, int CommissionReputation)
{
    const int Pressure = std::max(0, std::clamp(TaxRate, 0, MaximumTax) - BaselineTax);
    const int Waste = (Pressure * std::clamp(AdminShare, 0, BasisPoints)) / BasisPoints;
    return {
        std::clamp(100 - Pressure / 15 - Waste / 40, 0, 100),
        std::clamp(100 - Pressure / 12 - Waste / 50, 0, 100),
        TaxRate >= PermitTax && Heat < EnforcementThreshold && CommissionReputation >= 0
    };
}
}
