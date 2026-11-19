#include "CivicCampaignRules.h"

#include <cassert>
#include <cstdint>
#include <iostream>
#include <limits>

int main()
{
    using namespace RVA::Campaign;
    Totals ledger;
    assert(ApplyOnce(ledger, Outcome{5, 2, 1}));
    assert(ledger.Helped == 5 && ledger.Harmed == 2 && ledger.Collateral == 1);

    assert(!ApplyOnce(ledger, Outcome{-1, 0, 0}));
    assert(ledger.Helped == 5 && ledger.Harmed == 2);
    assert(!ApplyOnce(ledger, Outcome{1, -5, 0}));
    assert(!ApplyOnce(ledger, Outcome{0, 0, -2}));
    assert(ledger.Collateral == 1);

    assert(ClampStrain(0, 999) == 3);
    assert(ClampStrain(3, -999) == 0);
    assert(ClampStrain(1, 1) == 2);
    assert(ClampComplianceTier(0, 99) == 4);
    assert(ClampComplianceTier(4, -99) == 0);
    assert(ClampComplianceTier(2, 1) == 3);

    assert(!ThirdAlignmentEligible(1, 2, false));
    assert(ThirdAlignmentEligible(1, 2, true));
    assert(!ThirdAlignmentEligible(3, 2, true));
    assert(!ThirdAlignmentEligible(0, -1, true));
    assert(FixerEligible(8, 8, true));
    assert(!FixerEligible(7, 8, true));
    assert(!FixerEligible(8, 8, false));
    assert(!FixerEligible(8, -1, true));

    Totals maximum{std::numeric_limits<std::int64_t>::max(), 0, 0};
    assert(!ApplyOnce(maximum, Outcome{1, 1, 0}));
    assert(maximum.Harmed == 0); // failed update must remain atomic

    std::cout << "PASS: v2 campaign ledger and eligibility rules\n";
}
