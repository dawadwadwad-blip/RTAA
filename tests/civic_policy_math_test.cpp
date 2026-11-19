#include "CivicPolicyMath.h"

#include <cassert>
#include <cstdio>
#include <limits>

using namespace RVA::CivicPolicy;

static_assert(BoundedReputation(95, 30) == 100);
static_assert(BoundedReputation(-96, -30) == -100);
static_assert(BoundedReputation(0, std::numeric_limits<int>::max()) == 100);
static_assert(RivalResponse(BoundedReputation(90, 60) - 90) == -5);
static_assert(RivalResponse(-16) == 8);
static_assert(Allocate(1'000'000, 425) == 42'500);
static_assert(Allocate(42'500, 9500) == 40'375);
static_assert(Allocate(42'500, 9500) + 2125 == 42'500);
static_assert(Allocate(std::numeric_limits<std::int64_t>::max(), 10000)
    == std::numeric_limits<std::int64_t>::max());
static_assert(Allocate(-500, 10000) == 0);
static_assert(!Evaluate(449, 9500, 0, 0).PermitsAvailable);
static_assert(Evaluate(450, 9500, 59, 0).PermitsAvailable);
static_assert(!Evaluate(450, 9500, 60, 0).PermitsAvailable);
static_assert(!Evaluate(450, 9500, 0, -1).PermitsAvailable);
static_assert(Evaluate(700, 9500, 0, 0).ResidentMorale < Evaluate(425, 9500, 0, 0).ResidentMorale);
static_assert(Evaluate(700, 9500, 0, 0).BusinessVitality < Evaluate(425, 9500, 0, 0).BusinessVitality);

int main()
{
    for (int Rate = 0; Rate <= MaximumTax; ++Rate)
    {
        const auto Receipts = Allocate(811'234, Rate);
        const auto Admin = Allocate(Receipts, 9500);
        assert(Admin >= 0 && Admin <= Receipts);
        assert(Receipts - Admin >= 0);
        const auto Policy = Evaluate(Rate, 9500, 0, 0);
        assert(Policy.ResidentMorale >= 0 && Policy.ResidentMorale <= 100);
        assert(Policy.BusinessVitality >= 0 && Policy.BusinessVitality <= 100);
    }
    std::puts("PASS: C++20 civic policy calculations, clamping, permit gates, and fiscal conservation");
}
