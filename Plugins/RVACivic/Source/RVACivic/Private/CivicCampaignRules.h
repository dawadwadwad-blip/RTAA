#pragma once

// Engine-independent arithmetic for the v2 Work Order outcome ledger.
// All tuning deltas are authored per job: Method Dial does not silently
// prescribe moral or enforcement consequences.
#include <algorithm>
#include <cstdint>
#include <limits>

namespace RVA::Campaign
{
struct Totals
{
    std::int64_t Helped = 0;
    std::int64_t Harmed = 0;
    std::int64_t Collateral = 0;
};

struct Outcome
{
    std::int32_t Helped = 0;
    std::int32_t Harmed = 0;
    std::int32_t Collateral = 0;
};

inline bool ApplyOnce(Totals& Current, const Outcome& Delta)
{
    if (Delta.Helped < 0 || Delta.Harmed < 0 || Delta.Collateral < 0)
    {
        return false;
    }

    const std::int64_t Max = std::numeric_limits<std::int64_t>::max();
    if (Current.Helped < 0 || Current.Harmed < 0 || Current.Collateral < 0
        || Current.Helped > Max - Delta.Helped
        || Current.Harmed > Max - Delta.Harmed
        || Current.Collateral > Max - Delta.Collateral)
    {
        return false;
    }

    Current.Helped += Delta.Helped;
    Current.Harmed += Delta.Harmed;
    Current.Collateral += Delta.Collateral;
    return true;
}

// District Strain is authored 0..3. Enforcement's numeric tier is 0..4;
// a jurisdiction handoff is a separate map rule rather than a sixth tier.
inline int ClampStrain(int Current, int Delta)
{
    return static_cast<int>(std::clamp(static_cast<std::int64_t>(Current) + Delta,
        std::int64_t{0}, std::int64_t{3}));
}

inline int ClampComplianceTier(int Current, int Delta)
{
    return static_cast<int>(std::clamp(static_cast<std::int64_t>(Current) + Delta,
        std::int64_t{0}, std::int64_t{4}));
}

inline bool ThirdAlignmentEligible(std::int64_t Collateral, std::int64_t MaximumCollateral,
    bool HasBelieverContact)
{
    return Collateral >= 0 && MaximumCollateral >= 0
        && Collateral <= MaximumCollateral && HasBelieverContact;
}

inline bool FixerEligible(std::int64_t Collateral, std::int64_t MinimumCollateral,
    bool HasMeansContact)
{
    return Collateral >= 0 && MinimumCollateral >= 0
        && Collateral >= MinimumCollateral && HasMeansContact;
}
} // namespace RVA::Campaign
