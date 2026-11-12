"""Owner-bound V2 decisions on the existing Run and Approval tables."""
from dataclasses import dataclass
from uuid import UUID

from db.errors import NotVisible
from db.records import RunRecord
from strategy.campaign_package import check as check_package, recheck_at
from strategy.campaign_v2 import CampaignConflict, CampaignNotFound, inactive_reason


@dataclass(frozen=True)
class CampaignSnapshot:
    brand_id: UUID
    profile_id: UUID | None
    source_url: str
    brand_name: str
    run: RunRecord | None


class Campaigns:
    def __init__(self, factory, actor, clock):
        self.factory = factory
        self.actor = actor
        self.clock = clock

    def _brand(self, uow, domain, *, lock=False):
        try:
            brand = uow.brands.get_visible(user_id=self.actor, domain_key=domain, lock=lock)
        except NotVisible:
            raise CampaignNotFound() from None
        if brand.owner_id != self.actor:
            raise CampaignNotFound()
        return brand

    def _latest(self, uow, brand):
        return uow.runs.current_successful(brand_id=brand.id, kind="campaign")

    def snapshot(self, domain):
        with self.factory() as uow:
            brand = self._brand(uow, domain)
            run = self._latest(uow, brand)
            return CampaignSnapshot(brand.id, brand.current_profile_id, brand.source_url or "",
                                    brand.display_name or "", run)

    def view(self, domain):
        with self.factory() as uow:
            brand = self._brand(uow, domain, lock=True)
            return self._view(uow, brand, self._latest(uow, brand))

    def _view(self, uow, brand, run):
        if not run:
            return {"run_id": None, "proposal": None, "approved": False, "reason": None}
        approval = uow.approvals.latest_for_run(run.id)
        checked_at = self.clock()
        package = run.output.get("kind") == "SOURCE_CAMPAIGN"
        evaluate = check_package if package else inactive_reason
        reason = ("PROFILE_CHANGED" if run.input_profile_id != brand.current_profile_id
                  else evaluate(run.output, checked_at))
        return {"run_id": str(run.id), "profile_snapshot_id": str(run.input_profile_id),
                "proposal": run.output, "reason": reason, "checked_at": checked_at.isoformat(),
                **({"recheck_at": recheck_at(run.output).isoformat()} if package and not reason else {}),
                "decision": approval.decision if approval else None,
                "approved": not reason and approval is not None and approval.decision == "approved",
                "approval_id": str(approval.id) if approval else None}

    def write(self, domain, snapshot, result, *, revision=False):
        with self.factory() as uow:
            brand = self._brand(uow, domain, lock=True)
            current = self._latest(uow, brand)
            if brand.id != snapshot.brand_id or brand.current_profile_id != snapshot.profile_id:
                raise CampaignConflict("PROFILE_CHANGED")
            if (current.id if current else None) != (snapshot.run.id if snapshot.run else None):
                raise CampaignConflict("CAMPAIGN_CHANGED")
            if result is None:
                return self._view(uow, brand, current)
            run = uow.runs.create_live_for_locked_brand(
                brand_id=brand.id, kind="campaign", created_by_user_id=self.actor,
                status="succeeded", input_profile_id=snapshot.profile_id,
                output=result, output_schema_version=result["schema_version"],
                dependencies=[(current.id, "revises_campaign")] if revision else (),
            )
            response = self._view(uow, brand, run)
            uow.commit()
            return response

    def decide(self, domain, run_id, decision):
        with self.factory() as uow:
            brand = self._brand(uow, domain, lock=True)
            run = self._latest(uow, brand)
            if run is None or run.id != run_id:
                raise CampaignConflict("CAMPAIGN_CHANGED")
            view = self._view(uow, brand, run)
            if view["reason"]:
                raise CampaignConflict(view["reason"])
            if view["decision"] != decision:
                uow.approvals.create_live(brand_id=brand.id, run_id=run.id, actor_id=self.actor,
                                          subject_kind="campaign", decision=decision)
                view = self._view(uow, brand, run)
                if view["reason"]:
                    raise CampaignConflict(view["reason"])
                uow.commit()
            return view
