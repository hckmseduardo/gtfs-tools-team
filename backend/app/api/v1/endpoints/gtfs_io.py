"""GTFS Import/Export endpoints"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
import io
import uuid

from app.api import deps
from app.api.deps import get_db
from app.models.user import User, UserRole
from app.models.agency import Agency
from app.models.audit import AuditAction
from app.services.gtfs_service import gtfs_service
from app.services.gtfs_validator import GTFSValidator
from app.schemas.gtfs_import import (
    GTFSImportOptions,
    GTFSImportResult,
    GTFSExportOptions,
    GTFSExportResult,
    GTFSValidationResult,
    GTFSAnalysisResult,
    GTFSAgencyInfo,
    GTFSFileSummary,
    AgencyMatch,
)
from app.utils.audit import create_audit_log
from sqlalchemy import select, cast, String

router = APIRouter()


@router.post("/validate", response_model=GTFSValidationResult)
async def validate_gtfs_file(
    file: UploadFile = File(..., description="GTFS ZIP file to validate"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> GTFSValidationResult:
    """
    Validate a GTFS ZIP file without importing it.

    Checks for:
    - Required files present
    - Valid CSV format
    - Required fields present
    - Basic data integrity

    All authenticated users can validate GTFS files.
    """
    # Verify file is a ZIP
    if not file.filename or not file.filename.endswith('.zip'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a ZIP archive",
        )

    # Read file contents
    contents = await file.read()
    file_obj = io.BytesIO(contents)

    # Validate
    result = await gtfs_service.validate_gtfs_zip(file_obj, db)

    return result


@router.post("/analyze", response_model=GTFSAnalysisResult)
async def analyze_gtfs_file(
    file: UploadFile = File(..., description="GTFS ZIP file to analyze"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> GTFSAnalysisResult:
    """
    Analyze a GTFS ZIP file to extract agency information (Step 2 of import wizard).

    This endpoint:
    1. Validates the ZIP structure
    2. Extracts agency information from agency.txt
    3. Matches with existing agencies in the database
    4. Returns file statistics and a temporary upload ID for later import

    The file is stored temporarily and can be imported using the upload_id.
    """
    import zipfile
    import csv
    import tempfile
    import os
    from pathlib import Path
    from difflib import SequenceMatcher

    # Verify file is a ZIP
    if not file.filename or not file.filename.endswith('.zip'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a ZIP archive",
        )

    # Read file contents
    contents = await file.read()
    file_obj = io.BytesIO(contents)

    # Generate upload ID and save file temporarily
    upload_id = str(uuid.uuid4())
    temp_dir = Path(tempfile.gettempdir()) / "gtfs_uploads"
    temp_dir.mkdir(exist_ok=True)
    temp_file_path = temp_dir / f"{upload_id}.zip"

    with open(temp_file_path, 'wb') as f:
        f.write(contents)

    # Standard GTFS files
    REQUIRED_FILES = ["agency.txt", "stops.txt", "routes.txt", "trips.txt", "stop_times.txt"]
    OPTIONAL_FILES = [
        "calendar.txt", "calendar_dates.txt", "shapes.txt",
        "fare_attributes.txt", "fare_rules.txt", "feed_info.txt",
        "frequencies.txt", "transfers.txt", "pathways.txt",
        "levels.txt", "translations.txt", "attributions.txt"
    ]
    ALL_STANDARD_FILES = set(REQUIRED_FILES + OPTIONAL_FILES)

    agencies_in_file: list[GTFSAgencyInfo] = []
    files_summary: list[GTFSFileSummary] = []
    missing_files: list[str] = []
    extra_files: list[str] = []

    try:
        with zipfile.ZipFile(file_obj, 'r') as zf:
            file_list = zf.namelist()
            txt_files = [f for f in file_list if f.endswith('.txt') and not f.startswith('__MACOSX')]

            # Check for required files
            for req_file in REQUIRED_FILES:
                if req_file not in txt_files:
                    missing_files.append(req_file)

            # Check for extra files
            for txt_file in txt_files:
                if txt_file not in ALL_STANDARD_FILES:
                    extra_files.append(txt_file)

            # Parse agency.txt
            if "agency.txt" in txt_files:
                with zf.open("agency.txt") as agency_file:
                    reader = csv.DictReader(io.TextIOWrapper(agency_file, encoding='utf-8-sig'))
                    for row in reader:
                        agencies_in_file.append(GTFSAgencyInfo(
                            agency_id=row.get("agency_id"),
                            agency_name=row.get("agency_name", "Unknown Agency"),
                            agency_url=row.get("agency_url"),
                            agency_timezone=row.get("agency_timezone"),
                            agency_lang=row.get("agency_lang"),
                            agency_phone=row.get("agency_phone"),
                            agency_fare_url=row.get("agency_fare_url"),
                            agency_email=row.get("agency_email"),
                        ))

            # Get file summaries
            for txt_file in txt_files:
                try:
                    with zf.open(txt_file) as f:
                        reader = csv.DictReader(io.TextIOWrapper(f, encoding='utf-8-sig'))
                        columns = reader.fieldnames or []
                        row_count = sum(1 for _ in reader)
                        files_summary.append(GTFSFileSummary(
                            filename=txt_file,
                            row_count=row_count,
                            columns=list(columns),
                        ))
                except Exception:
                    # Skip files we can't parse
                    pass

    except zipfile.BadZipFile:
        # Clean up temp file
        if temp_file_path.exists():
            os.remove(temp_file_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid ZIP file",
        )

    # Find matching agencies in database
    matching_agencies: list[AgencyMatch] = []
    existing_agencies = await db.execute(select(Agency))
    all_agencies = existing_agencies.scalars().all()

    for gtfs_agency in agencies_in_file:
        for db_agency in all_agencies:
            match_score = 0.0
            match_reasons = []

            # Exact agency_id match (highest confidence)
            if gtfs_agency.agency_id and db_agency.agency_id:
                if gtfs_agency.agency_id == db_agency.agency_id:
                    match_score = 1.0
                    match_reasons.append(f"Exact agency_id match: {gtfs_agency.agency_id}")

            # Name similarity
            if gtfs_agency.agency_name and db_agency.name:
                name_ratio = SequenceMatcher(
                    None,
                    gtfs_agency.agency_name.lower(),
                    db_agency.name.lower()
                ).ratio()
                if name_ratio > 0.8:
                    if match_score < name_ratio:
                        match_score = name_ratio
                    match_reasons.append(f"Name similarity: {name_ratio:.0%}")

            # URL match
            if gtfs_agency.agency_url and db_agency.agency_url:
                if gtfs_agency.agency_url.rstrip('/').lower() == db_agency.agency_url.rstrip('/').lower():
                    if match_score < 0.9:
                        match_score = 0.9
                    match_reasons.append("Same agency URL")

            if match_score >= 0.5:
                # Avoid duplicates
                if not any(m.id == db_agency.id for m in matching_agencies):
                    matching_agencies.append(AgencyMatch(
                        id=db_agency.id,
                        name=db_agency.name,
                        slug=db_agency.slug,
                        agency_id=db_agency.agency_id,
                        match_score=match_score,
                        match_reason="; ".join(match_reasons),
                    ))

    # Sort matches by score
    matching_agencies.sort(key=lambda x: x.match_score, reverse=True)

    return GTFSAnalysisResult(
        upload_id=upload_id,
        filename=file.filename,
        file_size_bytes=len(contents),
        agencies_in_file=agencies_in_file,
        matching_agencies=matching_agencies,
        files_summary=files_summary,
        has_required_files=len(missing_files) == 0,
        missing_files=missing_files,
        extra_files=extra_files,
    )


@router.post("/import-from-upload")
async def import_gtfs_from_upload(
    upload_id: str = Query(..., description="Upload ID from analyze endpoint"),
    agency_id: int = Query(..., description="Agency ID to import data for (use 0 to create new)"),
    create_agency: bool = Query(False, description="Create new agency if agency_id is 0"),
    agency_name: Optional[str] = Query(None, description="Name for new agency (if creating)"),
    agency_timezone: Optional[str] = Query(None, description="Timezone for new agency (if creating)"),
    replace_existing: bool = Query(False, description="Replace existing GTFS data for this agency"),
    skip_shapes: bool = Query(False, description="Skip importing shapes.txt"),
    stop_on_error: bool = Query(False, description="Stop import if validation errors found"),
    feed_name: Optional[str] = Query(None, description="Name for the GTFS feed"),
    feed_description: Optional[str] = Query(None, description="Description for the GTFS feed"),
    feed_version: Optional[str] = Query(None, description="Version identifier for the GTFS feed"),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),  # Use basic auth, check permissions manually
):
    """
    Import a previously uploaded GTFS file (Step 4 of import wizard).

    Uses the upload_id from the analyze endpoint to find the previously uploaded file.
    Optionally creates a new agency if agency_id is 0 and create_agency is True.
    """
    import tempfile
    import os
    from pathlib import Path
    from slugify import slugify

    # Find the uploaded file
    temp_dir = Path(tempfile.gettempdir()) / "gtfs_uploads"
    temp_file_path = temp_dir / f"{upload_id}.zip"

    if not temp_file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload not found. Files expire after 1 hour. Please upload again.",
        )

    # Read the file
    with open(temp_file_path, 'rb') as f:
        contents = f.read()

    # Handle agency creation if needed
    created_new_agency = False
    if create_agency and agency_id == 0:
        if not agency_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="agency_name is required when creating a new agency",
            )

        # Create new agency
        new_agency = Agency(
            name=agency_name,
            slug=slugify(agency_name),
            agency_timezone=agency_timezone or "America/New_York",
            is_active=True,
        )
        db.add(new_agency)
        await db.commit()
        await db.refresh(new_agency)
        agency_id = new_agency.id
        created_new_agency = True

        # Add user to agency as AGENCY_ADMIN
        from app.models.agency import user_agencies
        await db.execute(
            user_agencies.insert().values(
                user_id=current_user.id,
                agency_id=agency_id,
                role=UserRole.AGENCY_ADMIN.value,
            )
        )
        await db.commit()

    # Verify agency exists
    agency_result = await db.execute(select(Agency).where(Agency.id == agency_id))
    agency = agency_result.scalar_one_or_none()

    if not agency:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agency not found",
        )

    # Verify user has access to this agency
    # Skip check if we just created the agency (user was added as AGENCY_ADMIN above)
    if not current_user.is_superuser and not created_new_agency:
        from app.models.agency import user_agencies
        from app.models.team import TeamMember, Workspace, workspace_agencies, TeamRole
        from sqlalchemy import or_

        # Check direct agency membership
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == agency_id,
            cast(user_agencies.c.role, String).in_([
                UserRole.AGENCY_ADMIN.value,
                UserRole.SUPER_ADMIN.value,
                UserRole.EDITOR.value
            ]),
        )
        membership_result = await db.execute(membership_query)
        has_direct_access = membership_result.first() is not None

        if not has_direct_access:
            # Check team-based access (Owner or Editor with workspace access)
            team_access = await db.execute(
                select(TeamMember.role)
                .select_from(TeamMember)
                .join(Workspace, TeamMember.team_id == Workspace.team_id)
                .join(workspace_agencies, Workspace.id == workspace_agencies.c.workspace_id)
                .where(
                    TeamMember.user_id == current_user.id,
                    workspace_agencies.c.agency_id == agency_id,
                    or_(
                        TeamMember.role == TeamRole.OWNER,
                        TeamMember.role == TeamRole.EDITOR,
                    )
                )
            )
            team_roles = team_access.scalars().all()

            if not team_roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to import data for this agency",
                )

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.IMPORT,
        entity_type="gtfs_import",
        entity_id=str(agency_id),
        description=f"Queued GTFS import for '{agency.name}' from upload {upload_id} ({len(contents)} bytes)",
        new_values={
            "upload_id": upload_id,
            "file_size": len(contents),
            "agency_id": agency_id,
            "replace_existing": replace_existing,
            "skip_shapes": skip_shapes,
            "stop_on_error": stop_on_error,
            "feed_name": feed_name,
            "feed_description": feed_description,
            "feed_version": feed_version,
        },
        agency_id=agency_id,
        request=request,
    )

    # Queue the import task
    from app.db.base import AsyncTask
    from app.models.task import TaskStatus, TaskType
    from app.tasks import import_gtfs

    task_record = AsyncTask(
        celery_task_id=str(uuid.uuid4()),
        task_name=f"Import GTFS for {agency.name}",
        description=f"Importing from upload {upload_id} ({len(contents)} bytes)",
        task_type=TaskType.IMPORT_GTFS.value,
        user_id=current_user.id,
        agency_id=agency_id,
        status=TaskStatus.PENDING.value,
        progress=0.0,
        input_data={
            "upload_id": upload_id,
            "file_size": len(contents),
            "agency_id": agency_id,
            "replace_existing": replace_existing,
            "skip_shapes": skip_shapes,
            "stop_on_error": stop_on_error,
            "feed_name": feed_name,
            "feed_description": feed_description,
            "feed_version": feed_version,
        },
    )

    db.add(task_record)
    await db.commit()
    await db.refresh(task_record)

    # Queue the Celery task
    celery_result = import_gtfs.apply_async(
        kwargs={
            "task_db_id": task_record.id,
            "file_content": contents,
            "agency_id": agency_id,
            "replace_existing": replace_existing,
            "validate_only": False,
            "skip_shapes": skip_shapes,
            "stop_on_error": stop_on_error,
            "feed_name": feed_name,
            "feed_description": feed_description,
            "feed_version": feed_version,
        }
    )

    # Update task record with Celery task ID
    task_record.celery_task_id = celery_result.id
    await db.commit()
    await db.refresh(task_record)

    # Clean up the temporary file (task has the content now)
    try:
        os.remove(temp_file_path)
    except Exception:
        pass  # Ignore cleanup errors

    # Return task information
    from app.schemas.task import TaskResponse
    return TaskResponse.model_validate(task_record)


@router.post("/validate-upload")
async def validate_uploaded_gtfs_file(
    upload_id: str = Query(..., description="Upload ID from analyze endpoint"),
    country_code: str = Query("", description="ISO country code for location-specific validations"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Queue MobilityData validation for a previously uploaded GTFS file (Step 3 of import wizard).

    Uses the upload_id from the analyze endpoint to find the previously uploaded file.
    """
    import tempfile
    from pathlib import Path

    # Find the uploaded file
    temp_dir = Path(tempfile.gettempdir()) / "gtfs_uploads"
    temp_file_path = temp_dir / f"{upload_id}.zip"

    if not temp_file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload not found. Files expire after 1 hour. Please upload again.",
        )

    # Read the file
    with open(temp_file_path, 'rb') as f:
        contents = f.read()

    filename = f"gtfs_{upload_id}.zip"

    # Create task record
    from app.db.base import AsyncTask
    from app.models.task import TaskStatus, TaskType
    from app.tasks import validate_gtfs_file_mobilitydata as validate_task

    task_record = AsyncTask(
        celery_task_id=str(uuid.uuid4()),
        task_name=f"Validate GTFS File: {filename}",
        description=f"Running MobilityData GTFS Validator on uploaded file",
        task_type=TaskType.VALIDATE_GTFS.value,
        user_id=current_user.id,
        agency_id=None,
        status=TaskStatus.PENDING.value,
        progress=0.0,
        input_data={
            "upload_id": upload_id,
            "filename": filename,
            "file_size": len(contents),
            "country_code": country_code,
            "validator": "mobilitydata",
            "pre_import": True,
        },
    )

    db.add(task_record)
    await db.commit()
    await db.refresh(task_record)

    # Queue the Celery task
    celery_result = validate_task.apply_async(
        kwargs={
            "task_db_id": task_record.id,
            "file_content": contents,
            "filename": filename,
            "country_code": country_code,
        },
        task_id=f"validate_upload_mobilitydata_{task_record.id}"
    )

    # Update task record with Celery task ID
    task_record.celery_task_id = celery_result.id
    await db.commit()

    return {
        "task_id": task_record.id,
        "celery_task_id": celery_result.id,
        "status": "queued",
        "message": "MobilityData validation queued. Track progress in Task Manager.",
        "upload_id": upload_id,
        "filename": filename,
        "validator": "mobilitydata",
    }


@router.post("/validate-mobilitydata")
async def validate_gtfs_file_mobilitydata(
    file: UploadFile = File(..., description="GTFS ZIP file to validate"),
    country_code: str = Query("", description="ISO country code for location-specific validations"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Queue MobilityData validation for a GTFS ZIP file before import.

    This endpoint allows validating a file BEFORE importing it, so users can
    see validation results and decide whether to proceed with the import.

    The validation runs asynchronously. Returns a task ID to track progress.
    When complete, the task result will contain the validation report.
    """
    import tempfile
    import os

    # Verify file is a ZIP
    if not file.filename or not file.filename.endswith('.zip'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a ZIP archive",
        )

    # Read file contents
    contents = await file.read()

    # Create task record
    from app.db.base import AsyncTask
    from app.models.task import TaskStatus, TaskType
    from app.tasks import validate_gtfs_file_mobilitydata as validate_task

    task_record = AsyncTask(
        celery_task_id=str(uuid.uuid4()),
        task_name=f"Validate GTFS File: {file.filename}",
        description=f"Running MobilityData GTFS Validator on uploaded file '{file.filename}'",
        task_type=TaskType.VALIDATE_GTFS.value,
        user_id=current_user.id,
        agency_id=None,  # Pre-import validation, no agency yet
        status=TaskStatus.PENDING.value,
        progress=0.0,
        input_data={
            "filename": file.filename,
            "file_size": len(contents),
            "country_code": country_code,
            "validator": "mobilitydata",
            "pre_import": True,
        },
    )

    db.add(task_record)
    await db.commit()
    await db.refresh(task_record)

    # Queue the Celery task
    celery_result = validate_task.apply_async(
        kwargs={
            "task_db_id": task_record.id,
            "file_content": contents,
            "filename": file.filename,
            "country_code": country_code,
        },
        task_id=f"validate_file_mobilitydata_{task_record.id}"
    )

    # Update task record with Celery task ID
    task_record.celery_task_id = celery_result.id
    await db.commit()

    return {
        "task_id": task_record.id,
        "celery_task_id": celery_result.id,
        "status": "queued",
        "message": "MobilityData validation queued. Track progress in Task Manager.",
        "filename": file.filename,
        "validator": "mobilitydata",
    }


@router.get("/validation-report/{validation_id}")
async def get_pre_import_validation_report(
    validation_id: str,
    report_type: str = Query(
        "branded", description="Type of report: 'branded' (custom HTML), 'original' (MobilityData HTML), or 'json'"
    ),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Get a pre-import validation report.

    Returns the validation report in the specified format.
    This is for reports generated during pre-import validation (before a feed exists).
    """
    from fastapi.responses import FileResponse
    from app.services.mobilitydata_validator import mobilitydata_validator

    # Get report path
    report_path = mobilitydata_validator.get_report_path(validation_id, report_type)

    if not report_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Validation report not found: {validation_id}",
        )

    if report_type == "json":
        import json
        with open(report_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        return FileResponse(
            path=str(report_path),
            media_type="text/html",
            filename=f"validation_report_{validation_id}.html",
        )


@router.get("/validation-file/{validation_id}")
async def get_validation_gtfs_file(
    validation_id: str,
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Download the GTFS file from a validation task.

    Returns the original GTFS ZIP file that was validated.
    """
    from fastapi.responses import FileResponse
    from pathlib import Path
    from app.services.mobilitydata_validator import mobilitydata_validator

    # Look for the GTFS file in the validation directory
    output_dir = mobilitydata_validator.output_base_path / validation_id
    if not output_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Validation not found: {validation_id}",
        )

    # Find the GTFS zip file in the directory
    zip_files = list(output_dir.glob("*.zip"))
    if not zip_files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"GTFS file not found for validation: {validation_id}",
        )

    gtfs_file = zip_files[0]  # Take the first zip file found

    return FileResponse(
        path=str(gtfs_file),
        media_type="application/zip",
        filename=gtfs_file.name,
    )


@router.post("/import")
async def import_gtfs_file(
    agency_id: int = Query(..., description="Agency ID to import data for"),
    file: UploadFile = File(..., description="GTFS ZIP file to import"),
    replace_existing: bool = Query(False, description="Replace existing GTFS data for this agency"),
    validate_only: bool = Query(False, description="Only validate, don't import"),
    skip_shapes: bool = Query(False, description="Skip importing shapes.txt"),
    stop_on_error: bool = Query(False, description="Stop import if validation errors found"),
    feed_name: Optional[str] = Query(None, description="Name for the GTFS feed"),
    feed_description: Optional[str] = Query(None, description="Description for the GTFS feed"),
    feed_version: Optional[str] = Query(None, description="Version identifier for the GTFS feed"),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_role(UserRole.AGENCY_ADMIN)),
):
    """
    Queue a GTFS import task.

    Process:
    1. Validate permissions and file format
    2. Create an AsyncTask record
    3. Queue the Celery task
    4. Return task information immediately

    The import runs asynchronously in the background.
    Check task status via the /tasks endpoints.

    Only agency admins and super admins can import data.
    """
    # Verify agency exists
    agency_result = await db.execute(select(Agency).where(Agency.id == agency_id))
    agency = agency_result.scalar_one_or_none()

    if not agency:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agency not found",
        )

    # Verify user has access to this agency (if not super admin)
    if not current_user.is_superuser:
        from app.models.agency import user_agencies
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == agency_id,
            cast(user_agencies.c.role, String).in_([UserRole.AGENCY_ADMIN.value, UserRole.SUPER_ADMIN.value]),
        )
        membership_result = await db.execute(membership_query)
        if not membership_result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to import data for this agency",
            )

    # Verify file is a ZIP
    if not file.filename or not file.filename.endswith('.zip'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a ZIP archive",
        )

    # Read file contents into memory
    contents = await file.read()

    # Create audit log for GTFS import
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.IMPORT,
        entity_type="gtfs_import",
        entity_id=str(agency_id),
        description=f"Queued GTFS import for '{agency.name}' from file '{file.filename}' ({len(contents)} bytes)",
        new_values={
            "filename": file.filename,
            "file_size": len(contents),
            "agency_id": agency_id,
            "replace_existing": replace_existing,
            "validate_only": validate_only,
            "skip_shapes": skip_shapes,
            "stop_on_error": stop_on_error,
            "feed_name": feed_name,
            "feed_description": feed_description,
            "feed_version": feed_version,
        },
        agency_id=agency_id,
        request=request,
    )

    # Import task models (from db.base to ensure all models are loaded)
    from app.db.base import AsyncTask
    from app.models.task import TaskStatus, TaskType
    from app.tasks import import_gtfs

    # Create AsyncTask record
    task_record = AsyncTask(
        celery_task_id=str(uuid.uuid4()),  # Temporary ID, will be updated after queuing
        task_name=f"Import GTFS for {agency.name}",
        description=f"Importing {file.filename} ({len(contents)} bytes)",
        task_type=TaskType.IMPORT_GTFS.value,
        user_id=current_user.id,
        agency_id=agency_id,
        status=TaskStatus.PENDING.value,
        progress=0.0,
        input_data={
            "filename": file.filename,
            "file_size": len(contents),
            "agency_id": agency_id,
            "replace_existing": replace_existing,
            "validate_only": validate_only,
            "skip_shapes": skip_shapes,
            "stop_on_error": stop_on_error,
            "feed_name": feed_name,
            "feed_description": feed_description,
            "feed_version": feed_version,
        },
    )

    db.add(task_record)
    await db.commit()
    await db.refresh(task_record)

    # Queue the Celery task
    celery_result = import_gtfs.apply_async(
        kwargs={
            "task_db_id": task_record.id,
            "file_content": contents,
            "agency_id": agency_id,
            "replace_existing": replace_existing,
            "validate_only": validate_only,
            "skip_shapes": skip_shapes,
            "stop_on_error": stop_on_error,
            "feed_name": feed_name,
            "feed_description": feed_description,
            "feed_version": feed_version,
        }
    )

    # Update task record with Celery task ID
    task_record.celery_task_id = celery_result.id
    await db.commit()
    await db.refresh(task_record)

    # Return task information
    from app.schemas.task import TaskResponse
    return TaskResponse.model_validate(task_record)


@router.get("/export", response_class=StreamingResponse)
async def export_gtfs_file(
    agency_id: int = Query(..., description="Agency ID to export data for"),
    feed_id: Optional[int] = Query(None, description="Specific feed ID to export (uses active feed if not specified)"),
    include_shapes: bool = Query(True, description="Include shapes.txt in export"),
    include_calendar_dates: bool = Query(True, description="Include calendar_dates.txt in export"),
    validate_before_export: bool = Query(False, description="Run validation before export"),
    fail_on_validation_errors: bool = Query(False, description="Fail export if validation has errors"),
    date_filter_start: Optional[str] = Query(None, pattern=r"^\d{8}$", description="Start date filter (YYYYMMDD)"),
    date_filter_end: Optional[str] = Query(None, pattern=r"^\d{8}$", description="End date filter (YYYYMMDD)"),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> StreamingResponse:
    """
    Export GTFS data for an agency as a ZIP file.

    All authenticated users with access to the agency can export data.

    - **validate_before_export**: If true, runs GTFS validation before exporting
    - **fail_on_validation_errors**: If true and validation has errors, export will fail
    """
    # Verify agency exists
    agency_result = await db.execute(select(Agency).where(Agency.id == agency_id))
    agency = agency_result.scalar_one_or_none()

    if not agency:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agency not found",
        )

    # Verify user has access to this agency (if not super admin)
    if not current_user.is_superuser:
        from app.models.agency import user_agencies
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == agency_id,
        )
        membership_result = await db.execute(membership_query)
        if not membership_result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this agency",
            )

    # Run validation before export if requested
    if validate_before_export:
        from app.models.gtfs import GTFSFeed
        from app.services.gtfs_validator import GTFSValidator

        # Find the feed to validate
        if feed_id:
            feed_query = select(GTFSFeed).where(GTFSFeed.id == feed_id, GTFSFeed.agency_id == agency_id)
        else:
            # Use the most recently imported active feed for this agency
            feed_query = select(GTFSFeed).where(
                GTFSFeed.agency_id == agency_id,
                GTFSFeed.is_active == True
            ).order_by(GTFSFeed.imported_at.desc()).limit(1)

        feed_result = await db.execute(feed_query)
        feed = feed_result.scalar_one_or_none()

        if feed:
            validator = GTFSValidator(db)
            validation_result = await validator.validate_feed(feed.id)

            if fail_on_validation_errors and not validation_result.is_valid():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": "Export failed due to validation errors",
                        "error_count": validation_result.error_count,
                        "warning_count": validation_result.warning_count,
                        "issues": [issue.to_dict() for issue in validation_result.issues[:10]],
                        "summary": validation_result._generate_summary(),
                    }
                )

    # Create export options
    options = GTFSExportOptions(
        agency_id=agency_id,
        feed_id=feed_id,
        include_shapes=include_shapes,
        include_calendar_dates=include_calendar_dates,
        date_filter_start=date_filter_start,
        date_filter_end=date_filter_end,
    )

    # Export
    zip_bytes = await gtfs_service.export_gtfs_zip(options, db)

    # Create audit log for GTFS export
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.EXPORT,
        entity_type="gtfs_export",
        entity_id=str(agency_id),
        description=f"Exported GTFS data for '{agency.name}' ({len(zip_bytes)} bytes)",
        new_values={
            "agency_id": agency_id,
            "file_size": len(zip_bytes),
            "include_shapes": include_shapes,
            "include_calendar_dates": include_calendar_dates,
            "date_filter_start": date_filter_start,
            "date_filter_end": date_filter_end,
        },
        agency_id=agency_id,
        request=request,
    )

    # Create streaming response
    zip_buffer = io.BytesIO(zip_bytes)

    # Generate filename
    filename = f"gtfs_{agency.slug}.zip"

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Length": str(len(zip_bytes)),
        }
    )


@router.post("/validate-feed")
async def validate_feed(
    feed_id: int = Query(..., description="Feed ID to validate"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Validate an imported GTFS feed.

    Runs comprehensive validation rules:
    - Routes: valid agency references, no duplicate route_id, mandatory fields filled
    - Shapes: shape_dist_traveled validation, shape_pt_sequence validation, mandatory fields filled

    Returns detailed validation results with errors, warnings, and info messages.
    """
    # Verify feed exists
    from app.models.gtfs import GTFSFeed

    feed_result = await db.execute(select(GTFSFeed).where(GTFSFeed.id == feed_id))
    feed = feed_result.scalar_one_or_none()

    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    # Verify user has access to this feed's agency (if not super admin)
    if not current_user.is_superuser:
        from app.models.agency import user_agencies
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == feed.agency_id,
        )
        membership_result = await db.execute(membership_query)
        if not membership_result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this feed",
            )

    # Run validation
    validator = GTFSValidator(db)
    result = await validator.validate_feed(feed_id)

    return result.to_dict()


@router.post("/export-generate")
async def generate_gtfs_export(
    feed_id: int = Query(..., description="Feed ID to export"),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Generate a GTFS export asynchronously (Step 1 of export wizard).

    Creates a Celery task to:
    1. Export the feed to a temporary ZIP file
    2. Validate the ZIP using MobilityData validator
    3. Store both files for later download

    Returns task info to track progress.
    """
    from app.models.gtfs import GTFSFeed

    # Verify feed exists
    feed_result = await db.execute(select(GTFSFeed).where(GTFSFeed.id == feed_id))
    feed = feed_result.scalar_one_or_none()

    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    # Verify agency exists and user has access
    agency_result = await db.execute(select(Agency).where(Agency.id == feed.agency_id))
    agency = agency_result.scalar_one_or_none()

    if not agency:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agency not found",
        )

    # Verify user has access to this agency (if not super admin)
    if not current_user.is_superuser:
        from app.models.agency import user_agencies
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == feed.agency_id,
        )
        membership_result = await db.execute(membership_query)
        if not membership_result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this feed",
            )

    # Generate export ID
    export_id = str(uuid.uuid4())

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.EXPORT,
        entity_type="gtfs_export",
        entity_id=str(feed_id),
        description=f"Queued GTFS export for feed '{feed.name}' (ID: {feed_id})",
        new_values={
            "export_id": export_id,
            "feed_id": feed_id,
            "agency_id": feed.agency_id,
        },
        agency_id=feed.agency_id,
        request=request,
    )

    # Create task record
    from app.db.base import AsyncTask
    from app.models.task import TaskStatus, TaskType
    from app.tasks import generate_gtfs_export_task

    task_record = AsyncTask(
        celery_task_id=str(uuid.uuid4()),
        task_name=f"Export GTFS: {feed.name}",
        description=f"Generating and validating GTFS export for feed '{feed.name}'",
        task_type=TaskType.EXPORT_GTFS.value,
        user_id=current_user.id,
        agency_id=feed.agency_id,
        status=TaskStatus.PENDING.value,
        progress=0.0,
        input_data={
            "export_id": export_id,
            "feed_id": feed_id,
            "feed_name": feed.name,
            "agency_id": feed.agency_id,
            "agency_name": agency.name,
        },
    )

    db.add(task_record)
    await db.commit()
    await db.refresh(task_record)

    # Queue the Celery task
    celery_result = generate_gtfs_export_task.apply_async(
        kwargs={
            "task_db_id": task_record.id,
            "export_id": export_id,
            "feed_id": feed_id,
        },
        task_id=f"export_gtfs_{export_id}"
    )

    # Update task record with Celery task ID
    task_record.celery_task_id = celery_result.id
    await db.commit()

    return {
        "task_id": task_record.id,
        "celery_task_id": celery_result.id,
        "export_id": export_id,
        "status": "queued",
        "message": "GTFS export queued. Track progress in Task Manager.",
        "feed_id": feed_id,
        "feed_name": feed.name,
    }


@router.get("/export-download/{export_id}")
async def download_gtfs_export(
    export_id: str,
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Download a generated GTFS export (Step 3 of export wizard).

    Returns the GTFS ZIP file that was generated in the export task.
    """
    from fastapi.responses import FileResponse
    from pathlib import Path

    # Look for the export file in the validation output directory
    from app.services.mobilitydata_validator import mobilitydata_validator

    output_dir = mobilitydata_validator.output_base_path / f"export_{export_id}"
    if not output_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Export not found: {export_id}. It may have expired.",
        )

    # Find the GTFS zip file
    gtfs_file = output_dir / "gtfs.zip"
    if not gtfs_file.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="GTFS file not found. Export may still be in progress.",
        )

    # Read feed name from metadata if available
    metadata_file = output_dir / "metadata.json"
    filename = "gtfs_export.zip"
    if metadata_file.exists():
        import json
        try:
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
                feed_name = metadata.get("feed_name", "export")
                filename = f"gtfs_{feed_name.replace(' ', '_').lower()}.zip"
        except Exception:
            pass

    return FileResponse(
        path=str(gtfs_file),
        media_type="application/zip",
        filename=filename,
    )


@router.get("/export-report/{export_id}")
async def get_export_validation_report(
    export_id: str,
    report_type: str = Query(
        "branded", description="Type of report: 'branded' (custom HTML), 'original' (MobilityData HTML), or 'json'"
    ),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Get the validation report for a GTFS export (Step 2 of export wizard).

    Returns the validation report in the specified format.
    """
    from fastapi.responses import FileResponse
    from pathlib import Path

    # Look for the report in the export directory
    from app.services.mobilitydata_validator import mobilitydata_validator

    output_dir = mobilitydata_validator.output_base_path / f"export_{export_id}"
    if not output_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Export not found: {export_id}. It may have expired.",
        )

    # Determine report path based on type
    if report_type == "branded":
        report_path = output_dir / "report_branded.html"
    elif report_type == "original":
        report_path = output_dir / "report.html"
    elif report_type == "json":
        report_path = output_dir / "report.json"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid report type. Use 'branded', 'original', or 'json'.",
        )

    if not report_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Validation report not found. Export may still be in progress.",
        )

    if report_type == "json":
        import json
        with open(report_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        return FileResponse(
            path=str(report_path),
            media_type="text/html",
            filename=f"validation_report_{export_id}.html",
        )


@router.get("/export/stats", response_model=GTFSExportResult)
async def get_export_stats(
    agency_id: int = Query(..., description="Agency ID to get export stats for"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> GTFSExportResult:
    """
    Get statistics about what would be exported for an agency.

    Returns counts of routes, stops, trips, etc. without actually generating the ZIP file.
    """
    # Verify agency exists
    agency_result = await db.execute(select(Agency).where(Agency.id == agency_id))
    agency = agency_result.scalar_one_or_none()

    if not agency:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agency not found",
        )

    # Verify user has access to this agency (if not super admin)
    if not current_user.is_superuser:
        from app.models.agency import user_agencies
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == agency_id,
        )
        membership_result = await db.execute(membership_query)
        if not membership_result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this agency",
            )

    # Get counts for each GTFS entity
    from app.models.gtfs import Route, Stop, Trip, StopTime, Calendar, CalendarDate, Shape
    from sqlalchemy import func

    route_count = await db.scalar(
        select(func.count(Route.id)).where(Route.agency_id == agency_id)
    ) or 0

    stop_count = await db.scalar(
        select(func.count(Stop.id)).where(Stop.agency_id == agency_id)
    ) or 0

    trip_count = await db.scalar(
        select(func.count(Trip.trip_id)).where(Trip.agency_id == agency_id)
    ) or 0

    stop_time_count = await db.scalar(
        select(func.count(StopTime.id)).where(
            StopTime.trip_id.in_(
                select(Trip.trip_id).where(Trip.agency_id == agency_id)
            )
        )
    ) or 0

    calendar_count = await db.scalar(
        select(func.count(Calendar.id))
    ) or 0

    calendar_date_count = await db.scalar(
        select(func.count(CalendarDate.id))
    ) or 0

    shape_count = await db.scalar(
        select(func.count(Shape.id)).where(Shape.agency_id == agency_id)
    ) or 0

    return GTFSExportResult(
        success=True,
        agency_id=agency_id,
        route_count=route_count,
        stop_count=stop_count,
        trip_count=trip_count,
        stop_time_count=stop_time_count,
        calendar_count=calendar_count,
        calendar_date_count=calendar_date_count,
        shape_count=shape_count,
        file_size_bytes=0,  # Not applicable for stats
    )
