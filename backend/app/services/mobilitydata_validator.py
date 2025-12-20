"""
MobilityData GTFS Validator Service

Integrates the official MobilityData GTFS Validator (https://github.com/MobilityData/gtfs-validator)
to provide comprehensive validation of GTFS feeds.

The validator runs as a Docker container and produces:
- report.json: Machine-readable validation results
- report.html: Human-readable HTML report
- system_errors.json: Any system-level errors
"""

import asyncio
import json
import logging
import os
import re
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import docker
from docker.errors import ContainerError, ImageNotFound, APIError

logger = logging.getLogger(__name__)


class MobilityDataValidatorError(Exception):
    """Exception raised for validator errors"""
    pass


class MobilityDataValidator:
    """
    Service for running MobilityData GTFS Validator in a Docker container.

    The validator is run via CLI and produces JSON and HTML reports.
    """

    DOCKER_IMAGE = "ghcr.io/mobilitydata/gtfs-validator:latest"
    CONTAINER_NAME_PREFIX = "gtfs-validator-"
    # This path is mounted as a volume in docker-compose.yml (container path)
    OUTPUT_DIR = "/tmp/gtfs-validation-output"

    # Network to connect to for reaching the host's docker
    DOCKER_NETWORK = "gtfs-network"

    # Notice code descriptions for better understanding
    NOTICE_DESCRIPTIONS = {
        # Errors
        "block_trips_with_overlapping_stop_times": "Trips within the same block have overlapping stop times, which is physically impossible.",
        "csv_parsing_failed": "A CSV file could not be parsed. Check for malformed CSV syntax.",
        "decreasing_shape_distance": "Shape distances decrease along the route instead of increasing.",
        "decreasing_or_equal_stop_time_distance": "Stop time distances are not strictly increasing.",
        "duplicate_key": "A row has a duplicate primary key value.",
        "empty_file": "A required file exists but contains no data rows.",
        "foreign_key_violation": "A reference to another table has no matching record.",
        "inconsistent_agency_timezone": "Multiple agencies have different timezones, which is not allowed.",
        "invalid_color": "A color value is not a valid 6-character hex color.",
        "invalid_currency": "A currency code is not a valid ISO 4217 code.",
        "invalid_date": "A date is not in YYYYMMDD format.",
        "invalid_email": "An email address is not in a valid format.",
        "invalid_float": "A decimal number is not in a valid format.",
        "invalid_integer": "An integer is not in a valid format.",
        "invalid_language_code": "A language code is not a valid BCP 47 code.",
        "invalid_phone_number": "A phone number contains invalid characters.",
        "invalid_row_length": "A row has more or fewer columns than the header.",
        "invalid_time": "A time is not in HH:MM:SS format.",
        "invalid_timezone": "A timezone is not a valid IANA timezone.",
        "invalid_url": "A URL is not in a valid format.",
        "location_without_parent_station": "A stop with location_type > 0 has no parent_station.",
        "missing_feed_info_date": "Feed start/end dates are missing from feed_info.txt.",
        "missing_required_column": "A required column is missing from a file.",
        "missing_required_field": "A required field value is empty.",
        "missing_required_file": "A required GTFS file is missing from the archive.",
        "missing_trip_edge": "A trip is missing its first or last stop time.",
        "new_line_in_value": "A field value contains a newline character.",
        "number_out_of_range": "A numeric value is outside the allowed range.",
        "overlapping_frequency": "Two frequency entries for the same trip overlap in time.",
        "pathway_to_platform_with_boarding_areas": "A pathway leads to a platform that has boarding areas.",
        "pathway_to_wrong_location_type": "A pathway references a stop with an incompatible location_type.",
        "point_near_origin": "A coordinate is suspiciously close to (0,0).",
        "point_near_pole": "A coordinate is suspiciously close to the North or South pole.",
        "route_both_short_and_long_name_missing": "A route has neither short_name nor long_name.",
        "same_name_and_description_for_route": "A route's short_name and long_name are identical.",
        "shape_points_too_far": "Consecutive shape points are unrealistically far apart.",
        "start_and_end_range_equal": "A range has equal start and end dates.",
        "start_and_end_range_out_of_order": "A range's end date is before its start date.",
        "station_with_parent_station": "A station has a parent_station, which is not allowed.",
        "stop_time_with_arrival_before_previous_departure": "A stop's arrival time is before the previous stop's departure.",
        "stop_time_with_only_arrival_or_departure_time": "A stop_time has only arrival OR departure time.",
        "stop_times_out_of_order": "Stop times are not in chronological order.",
        "stop_without_zone_id": "A stop used by a fare rule has no zone_id.",
        "too_fast_travel": "Travel between stops is faster than possible.",
        "trip_with_no_stop_times": "A trip has no stop_times entries.",
        "unusable_trip": "A trip has fewer than 2 stop_times.",
        "wrong_parent_location_type": "A stop's parent has an incompatible location_type.",

        # Warnings
        "attribution_without_role": "An attribution entry has no role specified.",
        "duplicate_route_name": "Multiple routes have the same name.",
        "empty_column_name": "A column header is empty.",
        "equal_shape_distance_same_coordinates": "Shape points have the same distance but different coordinates.",
        "expired_calendar": "Service dates have already passed.",
        "fast_travel_between_consecutive_stops": "Travel speed between stops is unusually fast (but physically possible).",
        "fast_travel_between_far_stops": "Travel speed between distant stops is unusually fast.",
        "feed_expiration_date_7_days": "The feed expires within 7 days.",
        "feed_expiration_date_30_days": "The feed expires within 30 days.",
        "feed_info_lang_and_agency_lang_mismatch": "feed_info language doesn't match agency language.",
        "inconsistent_agency_lang": "Multiple agencies have different languages.",
        "leading_or_trailing_whitespace": "A field value has leading or trailing spaces.",
        "missing_feed_info_date_warning": "Feed validity dates are recommended but missing.",
        "missing_recommended_column": "A recommended column is missing.",
        "missing_recommended_field": "A recommended field value is empty.",
        "missing_recommended_file": "A recommended GTFS file is missing.",
        "missing_timepoint_column": "stop_times.txt is missing the timepoint column.",
        "missing_timepoint_value": "A stop_time is missing a timepoint value.",
        "more_than_one_entity": "A file that should have one row has multiple rows.",
        "non_ascii_or_non_printable_char": "A field contains non-ASCII or non-printable characters.",
        "pathway_dangling": "A pathway doesn't connect to any meaningful locations.",
        "pathway_loop": "A pathway creates a loop that doesn't help navigation.",
        "platform_without_parent_station": "A platform stop has no parent station.",
        "route_color_contrast": "Route text color has poor contrast with background.",
        "route_long_name_contains_short_name": "Route long_name redundantly includes short_name.",
        "route_short_name_too_long": "Route short_name exceeds recommended length.",
        "same_name_and_description_for_stop": "A stop's name and description are identical.",
        "same_route_and_agency_url": "A route uses the same URL as its agency.",
        "same_stop_and_agency_url": "A stop uses the same URL as an agency.",
        "same_stop_and_route_url": "A stop uses the same URL as a route.",
        "shape_unused": "A shape is defined but not used by any trip.",
        "stop_has_too_many_matches_for_shape": "A stop matches multiple points on a shape.",
        "stop_too_far_from_shape": "A stop is unusually far from its trip's shape.",
        "stop_too_far_from_trip_shape": "A stop is far from the shape of its trip.",
        "stop_without_stop_time": "A stop is defined but never used in stop_times.",
        "too_many_rows": "A file has an unusually large number of rows.",
        "transfer_with_invalid_stop_location_type": "A transfer references stops with incompatible types.",
        "transfer_with_invalid_trip_and_route": "A transfer references incompatible trip and route.",
        "trip_coverage_not_active_for_next_7_days": "No trips are active for the next 7 days.",
        "unexpected_enum_value": "A field has an unexpected enumeration value.",
        "unknown_column": "A file contains an unrecognized column.",
        "unknown_file": "The archive contains an unrecognized file.",
        "unused_shape": "A shape is defined but not referenced by any trip.",
        "unused_trip": "A trip is defined but has no valid service.",

        # Info
        "duplicate_fare_rule_zone_id_fields": "Multiple fare rules have identical zone IDs.",
        "empty_row": "A row in a file is completely empty.",
        "mixed_case_recommended_field": "A field value uses mixed case when lowercase is recommended.",
        "non_standard_header": "A file has a non-standard column header.",
    }

    # Environment variable for host path (needed for Docker-in-Docker volume mounts)
    HOST_PATH_ENV_VAR = "GTFS_VALIDATION_HOST_PATH"

    # Standard GTFS files (errors in other files should be downgraded to warnings)
    GTFS_STANDARD_FILES = {
        "agency.txt",
        "stops.txt",
        "routes.txt",
        "trips.txt",
        "stop_times.txt",
        "calendar.txt",
        "calendar_dates.txt",
        "fare_attributes.txt",
        "fare_rules.txt",
        "fare_products.txt",
        "fare_leg_rules.txt",
        "fare_transfer_rules.txt",
        "fare_media.txt",
        "areas.txt",
        "stop_areas.txt",
        "shapes.txt",
        "frequencies.txt",
        "transfers.txt",
        "pathways.txt",
        "levels.txt",
        "feed_info.txt",
        "translations.txt",
        "attributions.txt",
        "timeframes.txt",
        "rider_categories.txt",
        "fare_containers.txt",
        "booking_rules.txt",
        "location_groups.txt",
        "location_group_stops.txt",
        "networks.txt",
        "route_networks.txt",
    }

    def __init__(self):
        self.output_base_path = Path(self.OUTPUT_DIR)
        self.output_base_path.mkdir(parents=True, exist_ok=True)
        # Get host path for Docker-in-Docker volume mounts
        self.host_base_path = os.environ.get(self.HOST_PATH_ENV_VAR)
        if self.host_base_path:
            logger.info(f"Using host path for validation: {self.host_base_path}")
        else:
            # Fallback to container path (works when not running in Docker)
            self.host_base_path = self.OUTPUT_DIR
            logger.warning(f"Host path not set, using container path: {self.host_base_path}")

    async def validate_feed_file(
        self,
        gtfs_zip_path: str,
        feed_name: str = "gtfs-feed",
        country_code: str = "",
    ) -> Dict[str, Any]:
        """
        Validate a GTFS feed file using MobilityData validator.

        Args:
            gtfs_zip_path: Path to the GTFS ZIP file
            feed_name: Name to identify the feed in reports
            country_code: Optional ISO country code for location-specific validations

        Returns:
            Dictionary containing:
            - success: bool
            - report_json: Parsed JSON report
            - report_html_path: Path to HTML report file
            - system_errors: List of system errors
            - validation_id: Unique ID for this validation
            - duration_seconds: Time taken for validation
        """
        validation_id = f"{feed_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        output_dir = self.output_base_path / validation_id
        output_dir.mkdir(parents=True, exist_ok=True)

        start_time = datetime.utcnow()

        try:
            # Run the validator container
            await self._run_validator_container(
                gtfs_zip_path=gtfs_zip_path,
                output_dir=str(output_dir),
                country_code=country_code,
                validation_id=validation_id,
            )

            duration = (datetime.utcnow() - start_time).total_seconds()

            # Parse results
            report_json = self._parse_json_report(output_dir / "report.json")
            system_errors = self._parse_system_errors(output_dir / "system_errors.json")

            # Filter notices: downgrade errors for non-GTFS files to warnings
            report_json = self._filter_notices_for_non_gtfs_files(report_json)

            # Generate custom branded HTML report
            custom_html_path = await self._generate_custom_html_report(
                report_json=report_json,
                validation_id=validation_id,
                feed_name=feed_name,
                output_dir=output_dir,
                duration_seconds=duration,
            )

            return {
                "success": True,
                "validation_id": validation_id,
                "report_json": report_json,
                "report_html_path": str(custom_html_path),
                "original_html_path": str(output_dir / "report.html"),
                "system_errors": system_errors,
                "duration_seconds": duration,
                "output_dir": str(output_dir),
            }

        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds()
            logger.error(f"Validation failed: {e}")
            return {
                "success": False,
                "validation_id": validation_id,
                "error": str(e),
                "duration_seconds": duration,
                "output_dir": str(output_dir),
            }

    async def validate_feed_url(
        self,
        gtfs_url: str,
        feed_name: str = "gtfs-feed",
        country_code: str = "",
    ) -> Dict[str, Any]:
        """
        Validate a GTFS feed from URL using MobilityData validator.

        Args:
            gtfs_url: URL to the GTFS ZIP file
            feed_name: Name to identify the feed in reports
            country_code: Optional ISO country code for location-specific validations

        Returns:
            Same as validate_feed_file
        """
        validation_id = f"{feed_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        output_dir = self.output_base_path / validation_id
        output_dir.mkdir(parents=True, exist_ok=True)

        start_time = datetime.utcnow()

        try:
            # Run the validator container with URL
            await self._run_validator_container(
                gtfs_url=gtfs_url,
                output_dir=str(output_dir),
                country_code=country_code,
                validation_id=validation_id,
            )

            duration = (datetime.utcnow() - start_time).total_seconds()

            # Parse results
            report_json = self._parse_json_report(output_dir / "report.json")
            system_errors = self._parse_system_errors(output_dir / "system_errors.json")

            # Filter notices: downgrade errors for non-GTFS files to warnings
            report_json = self._filter_notices_for_non_gtfs_files(report_json)

            # Generate custom branded HTML report
            custom_html_path = await self._generate_custom_html_report(
                report_json=report_json,
                validation_id=validation_id,
                feed_name=feed_name,
                output_dir=output_dir,
                duration_seconds=duration,
            )

            return {
                "success": True,
                "validation_id": validation_id,
                "report_json": report_json,
                "report_html_path": str(custom_html_path),
                "original_html_path": str(output_dir / "report.html"),
                "system_errors": system_errors,
                "duration_seconds": duration,
                "output_dir": str(output_dir),
            }

        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds()
            logger.error(f"Validation failed: {e}")
            return {
                "success": False,
                "validation_id": validation_id,
                "error": str(e),
                "duration_seconds": duration,
                "output_dir": str(output_dir),
            }

    def _container_to_host_path(self, container_path: str) -> str:
        """
        Translate a container path to the corresponding host path.

        This is needed when running Docker containers from within another container
        (Docker-in-Docker), as volume mounts must use host paths.

        Args:
            container_path: Path inside this container

        Returns:
            The corresponding path on the host machine
        """
        # Check if the path is under our validation output directory
        if container_path.startswith(self.OUTPUT_DIR):
            # Replace container base path with host base path
            relative_path = container_path[len(self.OUTPUT_DIR):]
            host_path = self.host_base_path + relative_path
            logger.debug(f"Translated path: {container_path} -> {host_path}")
            return host_path

        # Path is not in the shared directory - this may cause issues
        logger.warning(f"Path {container_path} is not in shared validation directory, "
                      f"volume mount may fail in Docker-in-Docker setup")
        return container_path

    async def _run_validator_container(
        self,
        output_dir: str,
        validation_id: str,
        gtfs_zip_path: Optional[str] = None,
        gtfs_url: Optional[str] = None,
        country_code: str = "",
    ) -> None:
        """
        Run the MobilityData validator Docker container using Docker SDK.

        Args:
            output_dir: Directory to store output files (container path)
            validation_id: Unique ID for container naming
            gtfs_zip_path: Path to local GTFS ZIP file (mutually exclusive with gtfs_url)
            gtfs_url: URL to GTFS ZIP file (mutually exclusive with gtfs_zip_path)
            country_code: Optional country code for validations
        """
        if not gtfs_zip_path and not gtfs_url:
            raise MobilityDataValidatorError("Either gtfs_zip_path or gtfs_url must be provided")

        # Sanitize container name - Docker only allows [a-zA-Z0-9][a-zA-Z0-9_.-]
        sanitized_id = re.sub(r'[^a-zA-Z0-9_.-]', '_', validation_id)
        container_name = f"{self.CONTAINER_NAME_PREFIX}{sanitized_id}"

        # Translate container paths to host paths for volume mounts
        # (needed for Docker-in-Docker setup)
        host_output_dir = self._container_to_host_path(output_dir)

        # Build volumes dict using HOST paths (not container paths)
        volumes = {
            host_output_dir: {"bind": "/output", "mode": "rw"}
        }

        # Build command args
        command_args = ["-o", "/output"]

        if gtfs_zip_path:
            # Translate input path to host path
            input_dir = os.path.dirname(os.path.abspath(gtfs_zip_path))
            input_filename = os.path.basename(gtfs_zip_path)
            host_input_dir = self._container_to_host_path(input_dir)
            volumes[host_input_dir] = {"bind": "/input", "mode": "ro"}
            command_args = ["-i", f"/input/{input_filename}"] + command_args
            logger.info(f"Input volume mount: {host_input_dir} -> /input")
        else:
            # Use URL
            command_args = ["-u", gtfs_url] + command_args

        logger.info(f"Output volume mount: {host_output_dir} -> /output")

        if country_code:
            command_args.extend(["-c", country_code])

        logger.info(f"Running validator container: {self.DOCKER_IMAGE} with args: {command_args}")

        # Use linux/amd64 platform since the image doesn't have ARM64 builds
        platform = "linux/amd64"

        # Run the container using Docker SDK
        def run_container():
            try:
                client = docker.from_env()

                # Pull image if not present (with platform specification)
                try:
                    client.images.get(self.DOCKER_IMAGE)
                except ImageNotFound:
                    logger.info(f"Pulling Docker image: {self.DOCKER_IMAGE} (platform: {platform})")
                    client.images.pull(self.DOCKER_IMAGE, platform=platform)

                # Run container with platform specification for ARM64 compatibility
                result = client.containers.run(
                    image=self.DOCKER_IMAGE,
                    command=command_args,
                    name=container_name,
                    volumes=volumes,
                    remove=True,
                    detach=False,
                    stdout=True,
                    stderr=True,
                    platform=platform,
                )
                return {"success": True, "output": result}
            except ContainerError as e:
                # Container ran but returned non-zero exit code
                # This is OK if the report was generated
                return {"success": False, "error": str(e), "exit_code": e.exit_status}
            except ImageNotFound as e:
                return {"success": False, "error": f"Image not found: {e}"}
            except APIError as e:
                return {"success": False, "error": f"Docker API error: {e}"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        # Run in thread pool to not block async loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, run_container)

        if not result["success"]:
            error_msg = result.get("error", "Unknown error")
            logger.error(f"Validator container failed: {error_msg}")
            # Don't raise if files were created (validator may return non-zero for validation errors)
            if not os.path.exists(os.path.join(output_dir, "report.json")):
                raise MobilityDataValidatorError(f"Validator failed: {error_msg}")

        logger.info(f"Validator completed for {validation_id}")

    def _parse_json_report(self, report_path: Path) -> Dict[str, Any]:
        """Parse the JSON validation report."""
        if not report_path.exists():
            return {"error": "Report file not found"}

        try:
            with open(report_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            return {"error": f"Failed to parse report: {e}"}

    def _parse_system_errors(self, errors_path: Path) -> List[Dict[str, Any]]:
        """Parse the system errors file."""
        if not errors_path.exists():
            return []

        try:
            with open(errors_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("notices", []) if isinstance(data, dict) else data
        except json.JSONDecodeError:
            return []

    def _filter_notices_for_non_gtfs_files(self, report_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Filter validation notices to remove notices for non-standard GTFS files.

        Files like __Licence.txt, version_chrono.txt, __MACOSX/, etc. are not part
        of the GTFS spec, so validation notices on them should be filtered out
        entirely as they are not relevant to GTFS validation.

        Args:
            report_json: The parsed validation report

        Returns:
            Modified report with non-GTFS file notices removed
        """
        notices = report_json.get("notices", [])
        filtered_notices = []
        removed_count = 0

        for notice in notices:
            # Check if this notice relates to a non-GTFS file
            sample_notices = notice.get("sampleNotices", [])
            filename = None

            # Try to extract filename from sample notices
            for sample in sample_notices:
                if "filename" in sample:
                    filename = sample.get("filename", "")
                    break

            # Also check the notice itself for filename
            if not filename:
                filename = notice.get("filename", "")

            # Check if this is a non-standard GTFS file
            is_non_gtfs_file = False
            if filename:
                # Normalize filename (remove path components)
                base_filename = filename.split("/")[-1] if "/" in filename else filename

                # Check if it's a standard GTFS file
                if base_filename not in self.GTFS_STANDARD_FILES:
                    # It's a non-standard file (e.g., __Licence.txt, __MACOSX/*, etc.)
                    is_non_gtfs_file = True

            # Filter out notices for non-GTFS files entirely
            if is_non_gtfs_file:
                removed_count += 1
                logger.info(f"Filtered out notice for non-GTFS file: {filename} (severity: {notice.get('severity')})")
            else:
                filtered_notices.append(notice)

        if removed_count > 0:
            logger.info(f"Filtered out {removed_count} notices for non-GTFS files")

        # Return modified report
        modified_report = report_json.copy()
        modified_report["notices"] = filtered_notices
        return modified_report

    async def _generate_custom_html_report(
        self,
        report_json: Dict[str, Any],
        validation_id: str,
        feed_name: str,
        output_dir: Path,
        duration_seconds: float,
    ) -> Path:
        """
        Generate a custom-branded HTML report from the validation results.

        Args:
            report_json: Parsed validation report
            validation_id: Unique validation ID
            feed_name: Name of the validated feed
            output_dir: Directory to save the report
            duration_seconds: Validation duration

        Returns:
            Path to the generated HTML report
        """
        # Extract summary from report
        summary = self._extract_summary(report_json)

        html_content = self._render_html_report(
            report_json=report_json,
            summary=summary,
            validation_id=validation_id,
            feed_name=feed_name,
            duration_seconds=duration_seconds,
        )

        output_path = output_dir / "report_branded.html"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        return output_path

    def _extract_summary(self, report_json: Dict[str, Any]) -> Dict[str, Any]:
        """Extract summary statistics from the validation report."""
        notices = report_json.get("notices", [])

        # Count by severity
        errors = [n for n in notices if n.get("severity") == "ERROR"]
        warnings = [n for n in notices if n.get("severity") == "WARNING"]
        infos = [n for n in notices if n.get("severity") == "INFO"]

        # Count by code
        codes = {}
        for notice in notices:
            code = notice.get("code", "unknown")
            if code not in codes:
                codes[code] = {"count": 0, "severity": notice.get("severity", "INFO")}
            codes[code]["count"] += 1

        return {
            "total_notices": len(notices),
            "error_count": len(errors),
            "warning_count": len(warnings),
            "info_count": len(infos),
            "is_valid": len(errors) == 0,
            "codes": codes,
            "validation_time": report_json.get("validationTimeSeconds", 0),
            "gtfs_features": report_json.get("gtfsFeatures", []),
            "agencies": report_json.get("agencies", []),
            "feed_info": report_json.get("feedInfo", {}),
        }

    def _render_html_report(
        self,
        report_json: Dict[str, Any],
        summary: Dict[str, Any],
        validation_id: str,
        feed_name: str,
        duration_seconds: float,
    ) -> str:
        """Render the custom HTML report."""

        notices = report_json.get("notices", [])

        # Group notices by code for better organization
        notices_by_code = {}
        for notice in notices:
            code = notice.get("code", "unknown")
            if code not in notices_by_code:
                notices_by_code[code] = {
                    "severity": notice.get("severity", "INFO"),
                    "notices": [],
                    "totalNotices": notice.get("totalNotices", 1),
                }
            notices_by_code[code]["notices"].append(notice)

        # Generate notice sections HTML
        notices_html = self._render_notices_sections(notices_by_code)

        # Generate summary cards
        status_class = "success" if summary["is_valid"] else "error"
        status_text = "Valid" if summary["is_valid"] else "Invalid"

        return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GTFS Validation Report - {feed_name}</title>
    <style>
        :root {{
            --primary-color: #228be6;
            --success-color: #40c057;
            --warning-color: #fab005;
            --error-color: #fa5252;
            --info-color: #228be6;
            --bg-color: #f8f9fa;
            --card-bg: #ffffff;
            --text-color: #212529;
            --text-muted: #868e96;
            --border-color: #dee2e6;
        }}

        @media (prefers-color-scheme: dark) {{
            :root {{
                --bg-color: #1a1b1e;
                --card-bg: #25262b;
                --text-color: #c1c2c5;
                --text-muted: #909296;
                --border-color: #373a40;
            }}
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            line-height: 1.6;
            padding: 2rem;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}

        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
            padding-bottom: 1rem;
            border-bottom: 2px solid var(--primary-color);
        }}

        .header h1 {{
            font-size: 1.75rem;
            color: var(--text-color);
        }}

        .header .brand {{
            font-size: 0.875rem;
            color: var(--text-muted);
        }}

        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}

        .summary-card {{
            background: var(--card-bg);
            padding: 1.5rem;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
            text-align: center;
        }}

        .summary-card h3 {{
            font-size: 0.875rem;
            color: var(--text-muted);
            margin-bottom: 0.5rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .summary-card .value {{
            font-size: 2rem;
            font-weight: 700;
        }}

        .summary-card.success .value {{ color: var(--success-color); }}
        .summary-card.error .value {{ color: var(--error-color); }}
        .summary-card.warning .value {{ color: var(--warning-color); }}
        .summary-card.info .value {{ color: var(--info-color); }}

        .status-badge {{
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 999px;
            font-size: 0.875rem;
            font-weight: 600;
        }}

        .status-badge.success {{
            background: var(--success-color);
            color: white;
        }}

        .status-badge.error {{
            background: var(--error-color);
            color: white;
        }}

        .section {{
            background: var(--card-bg);
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
            margin-bottom: 1.5rem;
            overflow: hidden;
        }}

        .section-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1rem 1.5rem;
            background: var(--bg-color);
            border-bottom: 1px solid var(--border-color);
            cursor: pointer;
        }}

        .section-header h2 {{
            font-size: 1rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}

        .severity-badge {{
            display: inline-block;
            padding: 0.125rem 0.5rem;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
        }}

        .severity-badge.ERROR {{ background: var(--error-color); color: white; }}
        .severity-badge.WARNING {{ background: var(--warning-color); color: #212529; }}
        .severity-badge.INFO {{ background: var(--info-color); color: white; }}

        .section-content {{
            padding: 1rem 1.5rem;
        }}

        .notice-list {{
            list-style: none;
        }}

        .notice-item {{
            padding: 0.75rem;
            border-bottom: 1px solid var(--border-color);
        }}

        .notice-item:last-child {{
            border-bottom: none;
        }}

        .notice-item code {{
            background: var(--bg-color);
            padding: 0.125rem 0.375rem;
            border-radius: 4px;
            font-size: 0.875rem;
        }}

        .notice-details {{
            margin-top: 0.5rem;
            font-size: 0.875rem;
            color: var(--text-muted);
        }}

        .meta-info {{
            display: flex;
            flex-wrap: wrap;
            gap: 1.5rem;
            margin-bottom: 2rem;
            font-size: 0.875rem;
            color: var(--text-muted);
        }}

        .meta-info span {{
            display: flex;
            align-items: center;
            gap: 0.25rem;
        }}

        .gtfs-features {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            margin-top: 0.5rem;
        }}

        .feature-tag {{
            background: var(--primary-color);
            color: white;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-size: 0.75rem;
        }}

        .collapsible {{
            display: none;
        }}

        .collapsible.open {{
            display: block;
        }}

        .toggle-icon {{
            transition: transform 0.2s;
        }}

        .toggle-icon.open {{
            transform: rotate(180deg);
        }}

        .footer {{
            margin-top: 2rem;
            padding-top: 1rem;
            border-top: 1px solid var(--border-color);
            text-align: center;
            font-size: 0.875rem;
            color: var(--text-muted);
        }}

        .footer a {{
            color: var(--primary-color);
            text-decoration: none;
        }}

        .footer a:hover {{
            text-decoration: underline;
        }}

        /* Notice descriptions and documentation links */
        .notice-description {{
            font-size: 0.95rem;
            color: var(--text-color);
            margin-bottom: 0.75rem;
            padding: 0.75rem;
            background: var(--bg-color);
            border-radius: 6px;
            border-left: 4px solid var(--primary-color);
        }}

        .doc-link {{
            display: inline-block;
            color: var(--primary-color);
            text-decoration: none;
            font-size: 0.875rem;
            margin-bottom: 1rem;
        }}

        .doc-link:hover {{
            text-decoration: underline;
        }}

        .notice-code {{
            font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
            font-size: 0.9rem;
        }}

        .header-right {{
            display: flex;
            align-items: center;
            gap: 1rem;
        }}

        .occurrence-count {{
            font-size: 0.875rem;
            color: var(--text-muted);
            font-weight: normal;
        }}

        .more-notices {{
            font-size: 0.875rem;
            color: var(--text-muted);
            font-style: italic;
            margin-top: 0.75rem;
            text-align: center;
        }}

        /* Data tables */
        .table-container {{
            overflow-x: auto;
            margin: 1rem 0;
            border-radius: 8px;
            border: 1px solid var(--border-color);
        }}

        .notices-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.8125rem;
            white-space: nowrap;
        }}

        .notices-table th {{
            background: var(--bg-color);
            padding: 0.625rem 0.75rem;
            text-align: left;
            font-weight: 600;
            color: var(--text-color);
            border-bottom: 2px solid var(--border-color);
            position: sticky;
            top: 0;
        }}

        .notices-table td {{
            padding: 0.5rem 0.75rem;
            border-bottom: 1px solid var(--border-color);
            color: var(--text-color);
        }}

        .notices-table tbody tr:hover {{
            background: var(--bg-color);
        }}

        .notices-table tbody tr:last-child td {{
            border-bottom: none;
        }}

        .row-number {{
            background: var(--primary-color);
            color: white;
            padding: 0.125rem 0.375rem;
            border-radius: 3px;
            font-size: 0.75rem;
            font-family: 'SF Mono', Monaco, monospace;
        }}

        .speed-value {{
            color: var(--warning-color);
            font-weight: 600;
        }}

        .empty-value {{
            color: var(--text-muted);
        }}

        /* Responsive improvements */
        @media (max-width: 768px) {{
            body {{
                padding: 1rem;
            }}

            .header {{
                flex-direction: column;
                align-items: flex-start;
                gap: 0.5rem;
            }}

            .summary-grid {{
                grid-template-columns: repeat(2, 1fr);
            }}

            .section-header {{
                flex-direction: column;
                align-items: flex-start;
                gap: 0.5rem;
            }}

            .header-right {{
                width: 100%;
                justify-content: space-between;
            }}
        }}

        @media print {{
            body {{
                background: white;
                padding: 1rem;
            }}
            .section-content {{
                display: block !important;
            }}
            .table-container {{
                overflow: visible;
            }}
            .notices-table {{
                white-space: normal;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h1>GTFS Validation Report</h1>
                <span class="brand">Generated by GTFS Editor</span>
            </div>
            <span class="status-badge {status_class}">{status_text}</span>
        </div>

        <div class="meta-info">
            <span><strong>Feed:</strong> {feed_name}</span>
            <span><strong>Validation ID:</strong> {validation_id}</span>
            <span><strong>Duration:</strong> {duration_seconds:.2f}s</span>
            <span><strong>Date:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</span>
        </div>

        <div class="summary-grid">
            <div class="summary-card {'success' if summary['is_valid'] else 'error'}">
                <h3>Status</h3>
                <div class="value">{status_text}</div>
            </div>
            <div class="summary-card error">
                <h3>Errors</h3>
                <div class="value">{summary['error_count']}</div>
            </div>
            <div class="summary-card warning">
                <h3>Warnings</h3>
                <div class="value">{summary['warning_count']}</div>
            </div>
            <div class="summary-card info">
                <h3>Info</h3>
                <div class="value">{summary['info_count']}</div>
            </div>
        </div>

        {self._render_feed_info_section(summary)}

        {notices_html}

        <div class="footer">
            <p>Validation powered by <a href="https://github.com/MobilityData/gtfs-validator" target="_blank">MobilityData GTFS Validator</a></p>
            <p>Report customized by GTFS Editor</p>
        </div>
    </div>

    <script>
        document.querySelectorAll('.section-header').forEach(header => {{
            header.addEventListener('click', () => {{
                const content = header.nextElementSibling;
                const icon = header.querySelector('.toggle-icon');
                content.classList.toggle('open');
                if (icon) icon.classList.toggle('open');
            }});
        }});

        // Open error sections by default
        document.querySelectorAll('.section.has-errors .section-content').forEach(content => {{
            content.classList.add('open');
        }});
    </script>
</body>
</html>'''

    def _render_feed_info_section(self, summary: Dict[str, Any]) -> str:
        """Render the feed info section."""
        feed_info = summary.get("feed_info", {})
        agencies = summary.get("agencies", [])
        features = summary.get("gtfs_features", [])

        if not feed_info and not agencies and not features:
            return ""

        agencies_html = ""
        if agencies:
            agencies_list = ", ".join(a.get("name", "Unknown") for a in agencies)
            agencies_html = f"<p><strong>Agencies:</strong> {agencies_list}</p>"

        features_html = ""
        if features:
            tags = "".join(f'<span class="feature-tag">{f}</span>' for f in features)
            features_html = f'<div class="gtfs-features">{tags}</div>'

        feed_info_details = ""
        if feed_info:
            details = []
            if feed_info.get("feedPublisherName"):
                details.append(f"<strong>Publisher:</strong> {feed_info['feedPublisherName']}")
            if feed_info.get("feedLang"):
                details.append(f"<strong>Language:</strong> {feed_info['feedLang']}")
            if feed_info.get("feedStartDate"):
                details.append(f"<strong>Start Date:</strong> {feed_info['feedStartDate']}")
            if feed_info.get("feedEndDate"):
                details.append(f"<strong>End Date:</strong> {feed_info['feedEndDate']}")
            feed_info_details = " | ".join(details)

        return f'''
        <div class="section">
            <div class="section-header">
                <h2>Feed Information</h2>
            </div>
            <div class="section-content open">
                {agencies_html}
                {f"<p>{feed_info_details}</p>" if feed_info_details else ""}
                {features_html}
            </div>
        </div>
        '''

    def _render_notices_sections(self, notices_by_code: Dict[str, Any]) -> str:
        """Render the notices sections grouped by code with descriptions and data tables."""
        if not notices_by_code:
            return '<div class="section"><div class="section-content open"><p>✅ No validation notices found. Your GTFS feed looks great!</p></div></div>'

        # Sort by severity (ERROR first, then WARNING, then INFO)
        severity_order = {"ERROR": 0, "WARNING": 1, "INFO": 2}
        sorted_codes = sorted(
            notices_by_code.items(),
            key=lambda x: (severity_order.get(x[1]["severity"], 3), x[0])
        )

        sections_html = ""
        for code, data in sorted_codes:
            severity = data["severity"]
            notices = data["notices"]
            count = data.get("totalNotices", len(notices))
            has_errors = "has-errors" if severity == "ERROR" else ""

            # Get description for this notice code
            description = self.NOTICE_DESCRIPTIONS.get(code, "")
            description_html = f'<p class="notice-description">{description}</p>' if description else ""

            # Get sample notices from the first notice
            sample_notices = []
            if notices and "sampleNotices" in notices[0]:
                sample_notices = notices[0].get("sampleNotices", [])[:15]  # Limit to 15 samples

            # Generate table for sample notices
            table_html = self._render_sample_notices_table(sample_notices, code)

            # Documentation link
            doc_url = f"https://gtfs-validator.mobilitydata.org/rules.html#{code}"
            doc_link = f'<a href="{doc_url}" target="_blank" class="doc-link">📖 View documentation</a>'

            sections_html += f'''
            <div class="section {has_errors}">
                <div class="section-header">
                    <h2>
                        <span class="severity-badge {severity}">{severity}</span>
                        <span class="notice-code">{code}</span>
                    </h2>
                    <div class="header-right">
                        <span class="occurrence-count">{count} occurrence{"s" if count != 1 else ""}</span>
                        <span class="toggle-icon">▼</span>
                    </div>
                </div>
                <div class="section-content collapsible">
                    {description_html}
                    {doc_link}
                    {table_html}
                    {f'<p class="more-notices">Showing {len(sample_notices)} of {count} occurrences</p>' if count > len(sample_notices) else ''}
                </div>
            </div>
            '''

        return sections_html

    def _render_sample_notices_table(self, sample_notices: List[Dict[str, Any]], code: str) -> str:
        """Render a table for sample notices with appropriate columns."""
        if not sample_notices:
            return ""

        # Get all unique keys from sample notices (excluding internal fields)
        all_keys = set()
        for notice in sample_notices:
            all_keys.update(notice.keys())

        # Define column order priority for common fields
        priority_fields = [
            "filename", "csvRowNumber", "fieldName", "fieldValue",
            "tripId", "routeId", "stopId", "shapeId", "serviceId", "agencyId",
            "stopName", "stopName1", "stopName2",
            "stopId1", "stopId2", "stopSequence", "stopSequence1", "stopSequence2",
            "arrivalTime", "departureTime", "arrivalTime1", "arrivalTime2", "departureTime1", "departureTime2",
            "speedKph", "distanceKm",
        ]

        # Order columns: priority fields first, then others alphabetically
        ordered_keys = []
        for key in priority_fields:
            if key in all_keys:
                ordered_keys.append(key)
                all_keys.discard(key)
        ordered_keys.extend(sorted(all_keys))

        # Build table header
        header_cells = "".join(f"<th>{self._format_column_name(key)}</th>" for key in ordered_keys)

        # Build table rows
        rows_html = ""
        for notice in sample_notices:
            cells = ""
            for key in ordered_keys:
                value = notice.get(key, "")
                formatted_value = self._format_cell_value(key, value)
                cells += f"<td>{formatted_value}</td>"
            rows_html += f"<tr>{cells}</tr>"

        return f'''
        <div class="table-container">
            <table class="notices-table">
                <thead>
                    <tr>{header_cells}</tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
        </div>
        '''

    def _format_column_name(self, key: str) -> str:
        """Format a column name for display."""
        # Convert camelCase to Title Case with spaces
        import re
        formatted = re.sub(r'([a-z])([A-Z])', r'\1 \2', key)
        formatted = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', formatted)
        return formatted.replace("_", " ").title()

    def _format_cell_value(self, key: str, value: Any) -> str:
        """Format a cell value for display."""
        if value is None or value == "":
            return '<span class="empty-value">—</span>'

        # Format specific value types
        if isinstance(value, float):
            if "speed" in key.lower() or "kph" in key.lower():
                return f'<span class="speed-value">{value:.1f} km/h</span>'
            elif "distance" in key.lower() or "km" in key.lower():
                return f'{value:.3f} km'
            else:
                return f'{value:.4f}'

        if isinstance(value, int):
            if "row" in key.lower():
                return f'<span class="row-number">Row {value}</span>'
            return str(value)

        # Truncate long strings
        str_value = str(value)
        if len(str_value) > 50:
            return f'<span title="{str_value}">{str_value[:47]}...</span>'

        return str_value

    async def cleanup_old_reports(self, max_age_hours: int = 24) -> int:
        """
        Clean up old validation reports.

        Args:
            max_age_hours: Maximum age of reports to keep

        Returns:
            Number of reports deleted
        """
        deleted = 0
        cutoff = datetime.utcnow().timestamp() - (max_age_hours * 3600)

        for item in self.output_base_path.iterdir():
            if item.is_dir():
                try:
                    if item.stat().st_mtime < cutoff:
                        shutil.rmtree(item)
                        deleted += 1
                except Exception as e:
                    logger.warning(f"Failed to delete {item}: {e}")

        return deleted

    def get_report_path(self, validation_id: str, report_type: str = "branded") -> Optional[Path]:
        """
        Get the path to a validation report.

        Args:
            validation_id: Validation ID
            report_type: "branded", "original", or "json"

        Returns:
            Path to the report file or None if not found
        """
        output_dir = self.output_base_path / validation_id

        if not output_dir.exists():
            return None

        if report_type == "branded":
            path = output_dir / "report_branded.html"
        elif report_type == "original":
            path = output_dir / "report.html"
        elif report_type == "json":
            path = output_dir / "report.json"
        else:
            return None

        return path if path.exists() else None


# Singleton instance
mobilitydata_validator = MobilityDataValidator()
