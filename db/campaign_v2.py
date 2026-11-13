"""Owner-bound V2 decisions on the existing Run and Approval tables."""
from dataclasses import dataclass
from uuid import UUID

from db.errors import ArchivedBrand, ForeignOwner, NotVisible
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

    def planning_snapshot(self, domain):
        with self.factory() as uow:
            ownership = uow.brands.owner_of(domain)
            if not ownership.exists:
                return None
            brand = self._brand(uow, domain)
            return CampaignSnapshot(brand.id, brand.current_profile_id, brand.source_url or "",
                                    brand.display_name or "", self._latest(uow, brand))

    def replay_plan(self, domain, request_id, inputs):
        with self.factory() as uow:
            brand = self._brand(uow, domain, lock=True)
            prior = uow.runs.campaign_for_request(brand_id=brand.id, request_id=str(request_id))
            if prior is None:
                return None
            if prior.output["planner"]["input"] != inputs:
                raise CampaignConflict("CAMPAIGN_REQUEST_MISMATCH")
            current = self._latest(uow, brand)
            if current.id != prior.id:
                raise CampaignConflict("CAMPAIGN_CHANGED")
            return self._view(uow, brand, current)

    def write_plan(self, domain, snapshot, result, url):
        if snapshot is not None:
            return self.write(domain, snapshot, result, revision=snapshot.run is not None)
        with self.factory() as uow:
            try:
                canonical = uow.brands.lock_or_create_for_scrape(
                    domain_key=domain, user_id=self.actor, display_name=result["brand_name"], source_url=url,
                )
            except (ArchivedBrand, ForeignOwner):
                raise CampaignNotFound() from None
            if not canonical.created:
                raise CampaignConflict("CAMPAIGN_CHANGED")
            brand = canonical.brand
            profile = uow.profiles.create_version_for_locked_brand(
                brand_id=brand.id, schema_version=1,
                profile={"source_url": url, "name": {"value": result["brand_name"], "source_type": "owner_input"}},
            )
            brand = uow.brands.set_current_profile(brand_id=brand.id, profile_id=profile.id)
            response = self._save(uow, brand, profile.id, result, None)
            uow.commit()
            return response

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
                **({"recheck_at": recheck_at(run.output).isoformat()} if package and reason in (None, "BRIEF_REVIEW_REQUIRED") else {}),
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
            response = self._save(uow, brand, snapshot.profile_id, result, current.id if revision else None)
            uow.commit()
            return response

    def _save(self, uow, brand, profile_id, result, previous_id):
        run = uow.runs.create_live_for_locked_brand(
            brand_id=brand.id, kind="campaign", created_by_user_id=self.actor,
            status="succeeded", input_profile_id=profile_id,
            output=result, output_schema_version=result["schema_version"],
            dependencies=[(previous_id, "revises_campaign")] if previous_id else (),
        )
        return self._view(uow, brand, run)

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
