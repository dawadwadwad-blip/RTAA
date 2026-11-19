#include "NightShiftProgress.h"

#include <cstdio>

using namespace RVA::NightShift;

constexpr bool FullRun(Exit Route, Segment First, Segment Second)
{
    Progress Order;
    return !Order.Paint(First) && !Order.BoardTruck() && !Order.ClearSite(Route) && !Order.Debrief()
        && Order.Brief() && !Order.Brief() && !Order.Paint(First)
        && Order.BoardTruck() && !Order.BoardTruck() && !Order.Paint(static_cast<Segment>(3))
        && Order.Paint(First) && !Order.Paint(First) && Order.GetCheckpoint().Current == Phase::Striping
        && Order.Paint(Second) && Order.GetCheckpoint().Current == Phase::Detour
        && !Order.Paint(Second) && !Order.ClearSite(Exit::None) && !Order.Debrief()
        && Order.ClearSite(Route) && !Order.ClearSite(Route)
        && Order.GetCheckpoint().Route == Route && Order.EvidenceCount() == 0
        && Order.Debrief() && Order.EvidenceCount() == 2 && !Order.Debrief();
}

constexpr bool ResumeCompletedRun()
{
    Progress Order;
    return Order.Restore({Phase::Complete, 3, Exit::Recovery})
        && Order.GetCheckpoint().Route == Exit::Recovery && Order.EvidenceCount() == 2
        && !Order.Paint(Segment::A) && !Order.ClearSite(Exit::Detour) && !Order.Debrief();
}

constexpr bool ResumeAfterOneStripe()
{
    Progress Order;
    return Order.Restore({Phase::Striping, 1, Exit::None})
        && !Order.Paint(Segment::A) && Order.Paint(Segment::B)
        && Order.GetCheckpoint().Current == Phase::Detour
        && Order.Restore({Phase::Detour, 3, Exit::None}) && !Order.Paint(Segment::B)
        && Order.ClearSite(Exit::Detour) && Order.Debrief();
}

constexpr bool RejectImpossibleCheckpoints()
{
    Progress Order;
    return !Order.Restore({Phase::Available, 2, Exit::None})
        && !Order.Restore({Phase::Briefed, 2, Exit::None})
        && !Order.Restore({Phase::Striping, 3, Exit::None})
        && !Order.Restore({Phase::Detour, 0, Exit::None})
        && !Order.Restore({Phase::Detour, 3, Exit::Detour})
        && !Order.Restore({Phase::ReturnToYard, 3, Exit::None})
        && !Order.Restore({Phase::Complete, 3, static_cast<Exit>(42)})
        && !Order.Restore({static_cast<Phase>(71), 0, Exit::None})
        && Order.GetCheckpoint().Current == Phase::Available;
}

static_assert(FullRun(Exit::Detour, Segment::A, Segment::B));
static_assert(FullRun(Exit::Recovery, Segment::B, Segment::A));
static_assert(ResumeCompletedRun());
static_assert(ResumeAfterOneStripe());
static_assert(RejectImpossibleCheckpoints());

int main()
{
    std::puts("PASS: Night Shift orders, both exits, retry, and one-time evidence");
}
