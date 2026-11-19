#include "StandingCommitteeProgress.h"

#include <cassert>
#include <cstdio>

using RVA::StandingCommittee::FavorProgress;
using RVA::StandingCommittee::Stage;

constexpr bool CanCompleteOnce()
{
    FavorProgress Favor;
    return Favor.GetStage() == Stage::Available
        && !Favor.Return()
        && Favor.Borrow()
        && Favor.GetStage() == Stage::Borrowed
        && !Favor.Borrow()
        && Favor.Return()
        && Favor.GetStage() == Stage::Returned
        && !Favor.Return()
        && !Favor.Borrow()
        && !Favor.LoseBorrower();
}

constexpr bool CanRetry()
{
    FavorProgress Favor;
    return !Favor.LoseBorrower() && Favor.Borrow() && Favor.LoseBorrower()
        && Favor.GetStage() == Stage::Available && !Favor.Return()
        && !Favor.LoseBorrower() && Favor.Borrow() && Favor.Return();
}

static_assert(CanCompleteOnce());
static_assert(CanRetry());

int main()
{
    assert(CanCompleteOnce());
    assert(CanRetry());
    std::puts("PASS: standing committee pickup, premature returns, completion, and retry");
}
