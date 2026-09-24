"""OBSOLETE one-off patch script - do not run.

It rewrote backend/intelligence.py with an early version of the routing /
OCR functions (which had the Attachment.file_path and unsorted-ranking bugs).
Those functions have since been fixed in backend/intelligence.py itself;
running this script would put the old bugs back.  Kept only for reference.
"""
raise SystemExit("update_intelligence.py is obsolete; backend/intelligence.py already contains the fixed code.")

import ast
with open('backend/intelligence.py', 'r') as f:
    code = f.read()

class FuncReplacer:
    def __init__(self, code):
        self.code = code
        self.tree = ast.parse(code)
    def replace_func(self, func_name, new_code):
        for node in self.tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == func_name:
                start = node.lineno - 1
                end = node.end_lineno
                lines = self.code.split('\n')
                return '\n'.join(lines[:start] + [new_code] + lines[end:])
        return self.code

new_gen_routing = """def generate_routing_suggestion(
    db: Session,
    doc_id: int,
    include_director_remark: bool = True,
    preferred_dept_id: Optional[int] = None,
    preferred_emp_id: Optional[int] = None
) -> Optional[models.RoutingSuggestion]:
    doc = get_document(db, doc_id)
    if not doc:
        return None

    depts = get_departments(db)
    suggested_dept_id: Optional[int] = preferred_dept_id or None
    suggested_emp_id: Optional[int] = preferred_emp_id

    ocr_record = db.query(models.DocumentOCR).filter(
        models.DocumentOCR.document_id == doc_id
    ).first()
    
    ocr_conf = ocr_record.confidence if (ocr_record and ocr_record.confidence and ocr_record.confidence > 0) else None
    confidence = ocr_conf if ocr_conf is not None else 0.0
    reason = "Routing intelligence confirmed during document intake verification." if (suggested_dept_id or suggested_emp_id) else "Insufficient content to determine department."
    source = RoutingSource.DOCUMENT_CONTENT if (suggested_dept_id or suggested_emp_id) else RoutingSource.SOURCE_METADATA
    is_director_instruction = False
    
    # Check Director Remark
    if include_director_remark and doc.latest_director_remark:
        remark_lower = doc.latest_director_remark.lower()
        employees = get_employees(db)
        for emp in employees:
            if emp.full_name.lower() in remark_lower:
                suggested_emp_id = emp.user_id
                suggested_dept_id = emp.department_id
                confidence = 0.95
                dept_name = emp.department.name if emp.department else "unknown"
                reason = f"Director remark explicitly names {emp.full_name} ({dept_name}) for assignment."
                source = RoutingSource.DIRECTOR_REMARK
                is_director_instruction = True
                break

        if not is_director_instruction:
            for dept in depts:
                if dept.name.lower() in remark_lower or (dept.code and dept.code.lower() in remark_lower):
                    suggested_dept_id = dept.id
                    confidence = 0.92
                    reason = f"Director remark explicitly references {dept.name} department."
                    source = RoutingSource.DIRECTOR_REMARK
                    is_director_instruction = True
                    break

    ranked_depts_json = []

    if not suggested_dept_id and not suggested_emp_id:
        is_ocr_ok = (ocr_record and ocr_record.ocr_status == OCRStatus.COMPLETED and bool(ocr_record.extracted_text and ocr_record.extracted_text.strip()))
        
        if is_ocr_ok:
            text_to_score = ocr_record.extracted_text
            text_lower = text_to_score.lower()
            
            # Semantic matching using OCR Adapter
            from backend.ocr_adapter import ocr_adapter
            if ocr_adapter.processor:
                # Prepare reference texts
                dept_map = {}
                ref_texts = []
                for d in depts:
                    desc = f"Department name: {d.name}"
                    if d.code:
                        desc += f" (code: {d.code})"
                    ref_texts.append(desc)
                    dept_map[desc] = d
                
                # Get similarities
                try:
                    res = ocr_adapter.process(doc.attachments[0].file_path if doc.attachments else "", reference_texts=ref_texts)
                    similarities = res.get("similarities", [])
                    
                    if similarities:
                        # similarities is a list of {"reference": ref_text, "similarity": float}
                        
                        # Populate ranked_depts_json
                        for sim in similarities:
                            matched_d = dept_map.get(sim["reference"])
                            if not matched_d:
                                # Fallback if text got truncated
                                for r, d in dept_map.items():
                                    if sim["reference"] in r or r in sim["reference"]:
                                        matched_d = d
                                        break
                            if matched_d:
                                ranked_depts_json.append({"department": matched_d.name, "score": sim["similarity"]})
                                
                        if ranked_depts_json:
                            best_sim = ranked_depts_json[0]
                            best_dept = next((d for d in depts if d.name == best_sim["department"]), None)
                            if best_dept:
                                suggested_dept_id = best_dept.id
                                confidence = best_sim["score"]
                                reason = f"Semantic matching of OCR text matched {best_dept.name} (score {confidence:.2f})."
                                source = RoutingSource.DOCUMENT_CONTENT
                except Exception as e:
                    print(f"Semantic matching failed: {e}")
            
            # Employee extraction fallback
            employees = get_employees(db)
            for emp in employees:
                if emp.full_name and len(emp.full_name) > 3 and emp.full_name.lower() in text_lower:
                    suggested_emp_id = emp.user_id
                    reason += f" Staff '{emp.full_name}' explicitly mentioned in document text."
                    break

    if not suggested_dept_id and not suggested_emp_id:
        suggested_dept_id = None
        confidence = 0.0
        reason = "OCR extraction did not yield a departmental keyword match. Manual review required."
        source = RoutingSource.SOURCE_METADATA

    suggestion = db.query(models.RoutingSuggestion).filter(
        models.RoutingSuggestion.document_id == doc_id
    ).first()

    if not suggestion:
        suggestion = models.RoutingSuggestion(
            document_id=doc_id,
            suggested_department_id=suggested_dept_id,
            suggested_employee_id=suggested_emp_id,
            routing_confidence=confidence,
            routing_reason=reason,
            routing_source=source,
            is_director_instruction=is_director_instruction,
            ranked_departments=ranked_depts_json,
            generated_at=datetime.now(),
        )
        db.add(suggestion)
    elif not suggestion.confirmed_at:
        suggestion.suggested_department_id = suggested_dept_id
        suggestion.suggested_employee_id = suggested_emp_id
        suggestion.routing_confidence = confidence
        suggestion.routing_reason = reason
        suggestion.routing_source = source
        suggestion.is_director_instruction = is_director_instruction
        suggestion.ranked_departments = ranked_depts_json
        suggestion.generated_at = datetime.now()

    db.commit()
    db.refresh(suggestion)
    return suggestion"""

code = FuncReplacer(code).replace_func('generate_routing_suggestion', new_gen_routing)

new_trigger = """def trigger_ocr_processing(
    db: Session,
    doc_id: int,
    intake_ocr_text: Optional[str] = None,
    intake_ocr_confidence: Optional[float] = None,
    preferred_dept_id: Optional[int] = None,
    preferred_emp_id: Optional[int] = None
) -> Optional[models.DocumentOCR]:
    doc = get_document(db, doc_id)
    if not doc:
        return None

    ocr_record = db.query(models.DocumentOCR).filter(
        models.DocumentOCR.document_id == doc_id
    ).first()

    if not ocr_record:
        ocr_record = models.DocumentOCR(
            document_id=doc_id,
            ocr_status=OCRStatus.PENDING,
            processed_at=datetime.now()
        )
        db.add(ocr_record)
        db.commit()
        db.refresh(ocr_record)

    # 1. Clear existing extracted fields for this document
    db.query(models.DocumentExtractedField).filter(
        models.DocumentExtractedField.document_id == doc_id
    ).delete()
    db.commit()

    # 2. Pick a file to OCR (or use provided text)
    file_path = ""
    if doc.attachments:
        file_path = doc.attachments[0].file_path

    from backend.ocr_adapter import ocr_adapter
    
    if intake_ocr_text:
        # Simple manual intake
        ocr_record.extracted_text = intake_ocr_text
        ocr_record.confidence = intake_ocr_confidence or 0.85
        ocr_record.ocr_status = OCRStatus.COMPLETED
        ocr_record.ocr_engine = "INTAKE_WEB_API"
        ocr_record.processed_at = datetime.now()
    elif _OCR_AVAILABLE and file_path:
        res = ocr_adapter.process(file_path)
        if res.get("success"):
            ocr_record.extracted_text = res.get("text")
            ocr_record.confidence = res.get("confidence")
            ocr_record.ocr_engine = res.get("engine")
            ocr_record.ocr_status = OCRStatus.COMPLETED
            
            # Save extracted fields
            extracted = res.get("extracted_fields", {})
            for fname, fval in extracted.items():
                if isinstance(fval, list):
                    fval = ", ".join([str(v) for v in fval])
                if fval:
                    field = models.DocumentExtractedField(
                        document_id=doc_id,
                        field_name=str(fname).upper(),
                        extracted_value=str(fval),
                        extracted_at=datetime.now(),
                        is_verified=False
                    )
                    db.add(field)
        else:
            ocr_record.ocr_status = OCRStatus.FAILED
            ocr_record.error_message = res.get("error")
    else:
        # Fallback
        ocr_record.extracted_text = doc.title
        ocr_record.confidence = 0.5
        ocr_record.ocr_status = OCRStatus.COMPLETED
        ocr_record.ocr_engine = "FALLBACK_METADATA"

    ocr_record.processed_at = datetime.now()
    db.commit()
    db.refresh(ocr_record)

    generate_routing_suggestion(
        db,
        doc_id,
        include_director_remark=True,
        preferred_dept_id=preferred_dept_id,
        preferred_emp_id=preferred_emp_id
    )

    return ocr_record"""
code = FuncReplacer(code).replace_func('trigger_ocr_processing', new_trigger)

with open('backend/intelligence.py', 'w') as f:
    f.write(code)
print("Done")
