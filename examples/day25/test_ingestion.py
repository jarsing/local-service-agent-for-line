"""Mock 模擬測試與本機 SQLite 測試；不驗證 Gemini 輸出能力。"""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from pydantic import ValidationError
from .fixtures import sample
from .schema import (PlaceExtraction, ReviewReceipt, validate_candidate,
    candidate_digest, required_review_fields, require_review)
from .store import open_db, admit, search_reviewed_places
from .capture import request_config, main as capture_main

class IngestionTests(unittest.TestCase):
    def setUp(self):
        self.source, self.item, self.raw = sample()
        self.valid = validate_candidate(self.raw, self.source)
        self.receipt = ReviewReceipt(source_sha256=self.source.sha256,
            candidate_sha256=candidate_digest(self.valid, self.source),
            reviewer="synthetic-local-test", approved=True,
            checked_fields=sorted(required_review_fields(self.valid)))
        base = Path("out/day25/tests")
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.root = Path(self.temp.name)
        self.db = open_db(self.root / "test.sqlite3")

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def invalid(self, **changes):
        item = {**self.item, **changes}
        with self.assertRaises((ValueError, ValidationError)):
            validate_candidate(json.dumps(item, ensure_ascii=False), self.source)

    def test_clear_text(self):
        self.assertEqual(self.valid.place_name, "測試店甲")

    def test_prose_hours_unknown(self):
        source, _, raw = sample("prose")
        self.assertIsNone(validate_candidate(raw, source).opening_hours_text)

    def test_prose_diet_unknown(self):
        source, _, raw = sample("prose")
        self.assertEqual(validate_candidate(raw, source).dietary_tags, [])

    def test_promotion_can_remain_in_source_but_not_value(self):
        source, item, raw = sample("noise")
        self.assertEqual(validate_candidate(raw, source).specialty_dishes, ["爌肉飯"])
        item["specialty_dishes"] = ["點擊領券"]
        with self.assertRaisesRegex(ValueError, "PROMOTIONAL_VALUE"):
            validate_candidate(json.dumps(item, ensure_ascii=False), source)

    def test_url_in_extracted_value_rejected(self):
        source, item, _ = sample("noise")
        item["specialty_dishes"] = ["https://example.invalid/"]
        with self.assertRaisesRegex(ValueError, "PROMOTIONAL_VALUE"):
            validate_candidate(json.dumps(item), source)

    def test_extra_approval_field(self): self.invalid(approved=True)
    def test_extra_url_field(self): self.invalid(coupon_url="https://example.invalid/")
    def test_wrong_name_type(self): self.invalid(place_name=123)
    def test_wrong_array_type(self): self.invalid(specialty_dishes="爌肉飯")
    def test_wrong_hours_status(self): self.invalid(hours_status="open_now")
    def test_empty_name(self): self.invalid(place_name="")
    def test_blank_quote(self): self.invalid(source_quote=" ")
    def test_missing_quote(self):
        item = copy.deepcopy(self.item)
        del item["source_quote"]
        with self.assertRaises(ValidationError):
            validate_candidate(json.dumps(item), self.source)
    def test_fabricated_quote(self): self.invalid(source_quote="測試店甲全年無休。")
    def test_fabricated_hours(self): self.invalid(opening_hours_text="24 小時營業")
    def test_fabricated_accessibility(self): self.invalid(accessibility_notes="輪椅可通行")
    def test_fabricated_diet(self): self.invalid(dietary_tags=["全素"])
    def test_unverified_hours_must_be_null(self): self.invalid(hours_status="unverified")
    def test_explicit_hours_need_text(self): self.invalid(opening_hours_text=None)
    def test_duplicate_dishes(self): self.invalid(specialty_dishes=["爌肉飯", "爌肉飯"])
    def test_source_cannot_be_blank(self):
        with self.assertRaises(ValidationError): self.source.__class__(source_id="a",source_ref="a",text="")
    def test_receipt_required(self):
        with self.assertRaisesRegex(ValueError,"REVIEW_NOT_APPROVED"):
            require_review(self.valid,self.source,self.receipt.model_copy(update={"approved":False}))
    def test_receipt_source_hash(self):
        with self.assertRaisesRegex(ValueError,"REVIEW_SOURCE_CHANGED"):
            require_review(self.valid,self.source,self.receipt.model_copy(update={"source_sha256":"bad"}))
    def test_receipt_candidate_hash(self):
        with self.assertRaisesRegex(ValueError,"REVIEW_CANDIDATE_CHANGED"):
            require_review(self.valid,self.source,self.receipt.model_copy(update={"candidate_sha256":"bad"}))
    def test_receipt_fields(self):
        with self.assertRaisesRegex(ValueError,"REVIEW_FIELDS_INCOMPLETE"):
            require_review(self.valid,self.source,self.receipt.model_copy(update={"checked_fields":[]}))
    def test_type_success_is_not_human_approval(self):
        self.assertEqual(self.db.execute("SELECT count(*) FROM places").fetchone()[0],0)
    def test_admission_and_readback(self):
        admit(self.db,self.raw,self.source,self.receipt)
        out=search_reviewed_places(self.db,keyword="爌肉飯")
        self.assertEqual(out["total"],1)
        self.assertEqual(out["places"][0]["source_sha256"],self.source.sha256)
        self.assertIsNone(out["places"][0]["open_now"])
    def test_repeat_same_candidate(self):
        first=admit(self.db,self.raw,self.source,self.receipt)
        self.assertEqual(first,admit(self.db,self.raw,self.source,self.receipt))
        self.assertEqual(self.db.execute("SELECT count(*) FROM places").fetchone()[0],1)
    def test_rejected_write_keeps_database_empty(self):
        with self.assertRaises(ValueError):
            admit(self.db,self.raw,self.source,self.receipt.model_copy(update={"approved":False}))
        self.assertEqual(self.db.execute("SELECT count(*) FROM places").fetchone()[0],0)
    def test_new_candidate_requires_new_review(self):
        changed={**self.item,"specialty_dishes":["爌肉飯"]}
        with self.assertRaisesRegex(ValueError,"REVIEW_CANDIDATE_CHANGED"):
            admit(self.db,json.dumps(changed),self.source,self.receipt)
    def test_dietary_filter_is_not_weakened(self):
        admit(self.db,self.raw,self.source,self.receipt)
        result=search_reviewed_places(self.db,dietary_type="vegan",keyword="爌肉飯")
        self.assertEqual(result["status"],"unsupported_filter")
        self.assertEqual(result["total"],0)
    def test_nearby_needs_area(self):
        self.assertEqual(search_reviewed_places(self.db,area="附近")["status"],"needs_area")
    def test_keyword_is_not_sql(self):
        admit(self.db,self.raw,self.source,self.receipt)
        self.assertEqual(search_reviewed_places(self.db,keyword="' OR 1=1 --")["total"],0)
    def test_gemini_config_uses_response_schema(self):
        cfg=request_config()
        self.assertEqual(cfg["response_json_schema"],PlaceExtraction.model_json_schema())
        self.assertEqual(cfg["response_mime_type"],"application/json")
        self.assertEqual(cfg["thinking_config"],{"thinking_level":"low"})
        self.assertEqual(cfg["automatic_function_calling"],{"disable":True})
    def test_gemini_config_has_no_legacy_sampling(self):
        self.assertFalse({"temperature","candidate_count","top_p","top_k"}&request_config().keys())
    def test_plan_does_not_call_model(self):
        f=self.root/"input.txt";f.write_text(self.source.text,encoding="utf-8")
        out=self.root/"plan"
        code=capture_main(["--source-file",str(f),"--source-id","synthetic-clear",
            "--source-ref","urn:local:synthetic:clear","--out",str(out)])
        self.assertEqual(code,0)
        record=json.loads((out/"record.json").read_text())
        self.assertEqual(record["external_model_calls"],0)
        self.assertFalse((out/"sdk_response.json").exists())
    def test_unapproved_capture_is_blocked(self):
        f=self.root/"input.txt";f.write_text(self.source.text,encoding="utf-8")
        out=self.root/"blocked"
        code=capture_main(["--source-file",str(f),"--source-id","synthetic-clear",
            "--source-ref","urn:local:synthetic:clear","--out",str(out),"--capture"])
        self.assertEqual(code,2)
        self.assertFalse((out/"sdk_response.json").exists())
    def test_negated_claim_requires_semantic_review(self):
        # 字面出現不能證明肯定句；這個反例刻意保留人工語意複核責任。
        source,item,_=sample("prose")
        text=source.text+"請注意：店內不提供全素。"
        source=source.model_copy(update={"text":text})
        item.update(dietary_tags=["全素"],source_quote=text)
        obj=validate_candidate(json.dumps(item),source)
        self.assertEqual(obj.dietary_tags,["全素"])
        with self.assertRaises(ValueError):
            require_review(obj,source,self.receipt.model_copy(update={"approved":False}))


class ReviewGuardTests(unittest.TestCase):
    def setUp(self):
        import shutil
        from .run_live import CASES
        self.CASES = CASES
        base = Path("out/day25/tests")
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.root = Path(self.temp.name)
        self.evidence_dir = self.root / "live"
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        canonical = Path(__file__).parent / "evidence" / "live"
        for c in self.CASES:
            cid = c["id"]
            shutil.copytree(canonical / cid, self.evidence_dir / cid)
        self.canonical_decisions = json.loads((canonical / "review_decisions.json").read_text(encoding="utf-8"))

    def tearDown(self):
        self.temp.cleanup()

    def write_decisions(self, doc: dict) -> Path:
        p = self.root / "decisions.json"
        p.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return p

    def test_decision_hash_required(self):
        from .run_live import review_cases
        doc = copy.deepcopy(self.canonical_decisions)
        del doc["decisions"][0]["source_sha256"]
        p = self.write_decisions(doc)
        with self.assertRaisesRegex(ValueError, "DECISION_HASH_REQUIRED"):
            review_cases(self.evidence_dir, decisions_file=p, force=True)

    def test_decision_hash_format_invalid(self):
        from .run_live import review_cases
        doc = copy.deepcopy(self.canonical_decisions)
        doc["decisions"][0]["source_sha256"] = "invalid_short_hash"
        p = self.write_decisions(doc)
        with self.assertRaisesRegex(ValueError, "INVALID_SOURCE_HASH"):
            review_cases(self.evidence_dir, decisions_file=p, force=True)

    def test_decision_hash_mismatch(self):
        from .run_live import review_cases
        doc = copy.deepcopy(self.canonical_decisions)
        doc["decisions"][0]["candidate_sha256"] = "0" * 64
        p = self.write_decisions(doc)
        with self.assertRaisesRegex(ValueError, "DECISION_CANDIDATE_HASH_MISMATCH"):
            review_cases(self.evidence_dir, decisions_file=p, force=True)

    def test_decision_contradiction_rejected(self):
        from .run_live import review_cases
        doc = copy.deepcopy(self.canonical_decisions)
        doc["decisions"][2]["approved"] = True  # L25-3 決策為 REJECT 但設為 True
        p = self.write_decisions(doc)
        with self.assertRaisesRegex(ValueError, "CONTRADICTORY_DECISION"):
            review_cases(self.evidence_dir, decisions_file=p, force=True)

    def test_decision_missing_cases_rejected(self):
        from .run_live import review_cases
        doc = copy.deepcopy(self.canonical_decisions)
        doc["decisions"] = doc["decisions"][:4]  # 缺少一題
        p = self.write_decisions(doc)
        with self.assertRaisesRegex(ValueError, "INCOMPLETE_DECISIONS"):
            review_cases(self.evidence_dir, decisions_file=p, force=True)

    def test_decision_duplicate_id_rejected(self):
        from .run_live import review_cases
        doc = copy.deepcopy(self.canonical_decisions)
        doc["decisions"].append(copy.deepcopy(doc["decisions"][0]))
        p = self.write_decisions(doc)
        with self.assertRaisesRegex(ValueError, "DUPLICATE_DECISION_ID"):
            review_cases(self.evidence_dir, decisions_file=p, force=True)

    def test_run_cases_refuses_overwrite_without_force(self):
        from .run_live import run_cases
        sum_file = self.evidence_dir / "summary.json"
        sum_file.write_text("{}", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            run_cases(self.evidence_dir, dry_run=False, force=False)

    def test_review_cases_refuses_overwrite_without_force(self):
        from .run_live import review_cases
        p = self.write_decisions(self.canonical_decisions)
        review_cases(self.evidence_dir, decisions_file=p, force=True)
        with self.assertRaises(FileExistsError):
            review_cases(self.evidence_dir, decisions_file=p, force=False)

    def test_total_token_mismatch_fails_cross_check(self):
        from .run_live import run_cases
        record_file = self.evidence_dir / "L25-1" / "record.json"
        rec = json.loads(record_file.read_text(encoding="utf-8"))
        rec["usage_metadata"]["totalTokenCount"] = 99999
        record_file.write_text(json.dumps(rec), encoding="utf-8")
        summary = run_cases(self.evidence_dir, dry_run=True, force=True)
        self.assertFalse(summary["total_tokens_cross_check_equal"])


if __name__ == "__main__":
    unittest.main()
