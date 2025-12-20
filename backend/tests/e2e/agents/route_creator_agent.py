"""
Route Creator E2E Test Agent

Playwright-based test agent that exercises the route creator functionality
through the UI, including authentication, agency setup, and route creation scenarios.
"""

import asyncio
import os
import re
from dataclasses import dataclass
from typing import Optional

from playwright.async_api import Page, async_playwright, expect


@dataclass
class TestConfig:
    """Configuration for test execution."""
    base_url: str = "http://localhost:5173"
    api_url: str = "http://localhost:8000"
    test_email: str = "test@example.com"
    test_password: str = "testpassword123"
    agency_name: str = "Demo Transit Agency"
    headless: bool = True
    slow_mo: int = 0  # ms between actions, useful for debugging


class LoginPage:
    """Page object for login functionality."""
    
    def __init__(self, page: Page):
        self.page = page
        self.email_input = page.locator('input[type="email"], input[name="email"]')
        self.password_input = page.locator('input[type="password"], input[name="password"]')
        self.submit_button = page.locator('button[type="submit"]')
    
    async def login(self, email: str, password: str) -> None:
        """Perform login with credentials."""
        await self.email_input.fill(email)
        await self.password_input.fill(password)
        await self.submit_button.click()
        # Wait for navigation away from login
        await self.page.wait_for_url(re.compile(r"^(?!.*login).*$"), timeout=10000)


class AgencyPage:
    """Page object for agency management."""
    
    def __init__(self, page: Page):
        self.page = page
    
    async def navigate_to_agencies(self) -> None:
        """Navigate to agency list/management page."""
        await self.page.goto("/agencies")
        await self.page.wait_for_load_state("networkidle")
    
    async def delete_agency_if_exists(self, agency_name: str) -> bool:
        """Delete agency by name if it exists. Returns True if deleted."""
        agency_row = self.page.locator(f'text="{agency_name}"').first
        if await agency_row.count() > 0:
            # Find and click delete button in same row
            delete_btn = agency_row.locator("..").locator('button:has-text("Delete"), [aria-label="Delete"]')
            if await delete_btn.count() > 0:
                await delete_btn.click()
                # Confirm deletion if dialog appears
                confirm_btn = self.page.locator('button:has-text("Confirm"), button:has-text("Yes")')
                if await confirm_btn.count() > 0:
                    await confirm_btn.click()
                await self.page.wait_for_load_state("networkidle")
                return True
        return False
    
    async def create_agency(self, name: str, timezone: str = "America/New_York") -> None:
        """Create a new agency."""
        create_btn = self.page.locator('button:has-text("Create"), button:has-text("New Agency")')
        await create_btn.click()
        
        # Fill agency form
        await self.page.locator('input[name="name"]').fill(name)
        
        # Select timezone if dropdown exists
        tz_select = self.page.locator('select[name="timezone"]')
        if await tz_select.count() > 0:
            await tz_select.select_option(timezone)
        
        # Submit
        await self.page.locator('button[type="submit"]').click()
        await self.page.wait_for_load_state("networkidle")
    
    async def select_agency(self, name: str) -> None:
        """Select an agency to work with."""
        await self.page.locator(f'text="{name}"').click()
        await self.page.wait_for_load_state("networkidle")


class RouteCreatorPage:
    """Page object for route creator functionality."""
    
    def __init__(self, page: Page):
        self.page = page
    
    async def navigate(self) -> None:
        """Navigate to route creator."""
        # Try common navigation patterns
        nav_link = self.page.locator('a:has-text("Routes"), [href*="route"]').first
        if await nav_link.count() > 0:
            await nav_link.click()
        else:
            await self.page.goto("/routes")
        await self.page.wait_for_load_state("networkidle")
    
    async def open_creator(self) -> None:
        """Open the route creation form/modal."""
        create_btn = self.page.locator('button:has-text("Create Route"), button:has-text("New Route")')
        await create_btn.click()
        await self.page.wait_for_selector('[data-testid="route-creator"], .route-creator, form')
    
    async def fill_basic_info(self, short_name: str, long_name: str, route_type: int = 3) -> None:
        """Fill basic route information."""
        await self.page.locator('input[name="route_short_name"], input[name="shortName"]').fill(short_name)
        await self.page.locator('input[name="route_long_name"], input[name="longName"]').fill(long_name)
        
        # Route type select (3 = bus by default)
        type_select = self.page.locator('select[name="route_type"], select[name="type"]')
        if await type_select.count() > 0:
            await type_select.select_option(str(route_type))
    
    async def add_stop(self, name: str, lat: float, lon: float) -> None:
        """Add a stop to the route."""
        add_stop_btn = self.page.locator('button:has-text("Add Stop")')
        await add_stop_btn.click()
        
        # Fill stop details in modal/form
        await self.page.locator('input[name="stop_name"], input[name="name"]').last.fill(name)
        await self.page.locator('input[name="stop_lat"], input[name="lat"]').last.fill(str(lat))
        await self.page.locator('input[name="stop_lon"], input[name="lon"]').last.fill(str(lon))
        
        # Confirm stop addition
        confirm_btn = self.page.locator('button:has-text("Add"), button:has-text("Save")').last
        if await confirm_btn.count() > 0:
            await confirm_btn.click()
    
    async def add_waypoint(self, lat: float, lon: float) -> None:
        """Add a waypoint (shape point) to the route."""
        # Click on map or use waypoint input
        waypoint_btn = self.page.locator('button:has-text("Add Waypoint")')
        if await waypoint_btn.count() > 0:
            await waypoint_btn.click()
            await self.page.locator('input[name="waypoint_lat"]').fill(str(lat))
            await self.page.locator('input[name="waypoint_lon"]').fill(str(lon))
            await self.page.locator('button:has-text("Confirm")').click()
    
    async def set_schedule(self, start_time: str, end_time: str, headway_mins: int) -> None:
        """Set route schedule parameters."""
        schedule_section = self.page.locator('[data-testid="schedule"], .schedule-section')
        
        await schedule_section.locator('input[name="start_time"]').fill(start_time)
        await schedule_section.locator('input[name="end_time"]').fill(end_time)
        await schedule_section.locator('input[name="headway"], input[name="frequency"]').fill(str(headway_mins))
    
    async def save_route(self) -> None:
        """Save the route."""
        save_btn = self.page.locator('button:has-text("Save Route"), button[type="submit"]')
        await save_btn.click()
        await self.page.wait_for_load_state("networkidle")
    
    async def verify_route_created(self, short_name: str) -> bool:
        """Verify route appears in list."""
        route_item = self.page.locator(f'text="{short_name}"')
        return await route_item.count() > 0


class RouteCreatorTestAgent:
    """
    Main test orchestrator for route creator E2E tests.
    
    Handles browser lifecycle, authentication, and test scenario execution.
    """
    
    def __init__(self, config: Optional[TestConfig] = None):
        self.config = config or TestConfig()
        self.page: Optional[Page] = None
        self.results: list[dict] = []
    
    async def setup(self) -> None:
        """Initialize browser and authenticate."""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.config.headless,
            slow_mo=self.config.slow_mo
        )
        self.context = await self.browser.new_context()
        self.page = await self.context.new_page()
        
        # Navigate to app and login
        await self.page.goto(self.config.base_url)
        login_page = LoginPage(self.page)
        await login_page.login(self.config.test_email, self.config.test_password)
    
    async def teardown(self) -> None:
        """Clean up browser resources."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    async def cleanup_demo_agencies(self) -> None:
        """Remove existing demo agencies for clean test state."""
        agency_page = AgencyPage(self.page)
        await agency_page.navigate_to_agencies()
        
        # Delete any existing demo agencies
        deleted = await agency_page.delete_agency_if_exists(self.config.agency_name)
        if deleted:
            print(f"Cleaned up existing agency: {self.config.agency_name}")
    
    async def setup_test_agency(self) -> None:
        """Create fresh test agency."""
        agency_page = AgencyPage(self.page)
        await agency_page.create_agency(self.config.agency_name)
        await agency_page.select_agency(self.config.agency_name)
        print(f"Created test agency: {self.config.agency_name}")
    
    async def run_scenario(self, name: str, scenario_fn) -> dict:
        """Execute a test scenario and record results."""
        result = {"name": name, "passed": False, "error": None}
        try:
            await scenario_fn()
            result["passed"] = True
            print(f"✓ {name}")
        except Exception as e:
            result["error"] = str(e)
            print(f"✗ {name}: {e}")
        self.results.append(result)
        return result
    
    # Test Scenarios
    
    async def scenario_basic_route(self) -> None:
        """Create a simple route with minimal configuration."""
        route_page = RouteCreatorPage(self.page)
        await route_page.navigate()
        await route_page.open_creator()
        await route_page.fill_basic_info("1", "Main Street Line")
        await route_page.save_route()
        assert await route_page.verify_route_created("1"), "Route not found after creation"
    
    async def scenario_route_with_stops(self) -> None:
        """Create route with multiple stops."""
        route_page = RouteCreatorPage(self.page)
        await route_page.navigate()
        await route_page.open_creator()
        await route_page.fill_basic_info("2", "Downtown Express")
        
        # Add stops along a route
        await route_page.add_stop("Central Station", 40.7128, -74.0060)
        await route_page.add_stop("City Hall", 40.7138, -74.0050)
        await route_page.add_stop("Park Avenue", 40.7148, -74.0040)
        
        await route_page.save_route()
        assert await route_page.verify_route_created("2"), "Route with stops not found"
    
    async def scenario_route_with_waypoints(self) -> None:
        """Create route with shape waypoints."""
        route_page = RouteCreatorPage(self.page)
        await route_page.navigate()
        await route_page.open_creator()
        await route_page.fill_basic_info("3", "Scenic Route")
        
        # Add waypoints for route shape
        await route_page.add_waypoint(40.7128, -74.0060)
        await route_page.add_waypoint(40.7135, -74.0055)
        await route_page.add_waypoint(40.7142, -74.0048)
        
        await route_page.save_route()
        assert await route_page.verify_route_created("3"), "Route with waypoints not found"
    
    async def scenario_route_with_schedule(self) -> None:
        """Create route with schedule configuration."""
        route_page = RouteCreatorPage(self.page)
        await route_page.navigate()
        await route_page.open_creator()
        await route_page.fill_basic_info("4", "Commuter Line")
        
        # Add stops
        await route_page.add_stop("Terminal A", 40.7128, -74.0060)
        await route_page.add_stop("Terminal B", 40.7200, -74.0000)
        
        # Set schedule
        await route_page.set_schedule("06:00", "22:00", 15)
        
        await route_page.save_route()
        assert await route_page.verify_route_created("4"), "Route with schedule not found"
    
    async def run_all_scenarios(self) -> list[dict]:
        """Execute all test scenarios."""
        scenarios = [
            ("Basic Route Creation", self.scenario_basic_route),
            ("Route with Stops", self.scenario_route_with_stops),
            ("Route with Waypoints", self.scenario_route_with_waypoints),
            ("Route with Schedule", self.scenario_route_with_schedule),
        ]
        
        for name, scenario_fn in scenarios:
            await self.run_scenario(name, scenario_fn)
        
        return self.results
    
    async def run(self) -> list[dict]:
        """Main entry point - run full test suite."""
        try:
            await self.setup()
            await self.cleanup_demo_agencies()
            await self.setup_test_agency()
            results = await self.run_all_scenarios()
            
            # Summary
            passed = sum(1 for r in results if r["passed"])
            total = len(results)
            print(f"\nResults: {passed}/{total} scenarios passed")
            
            return results
        finally:
            await self.teardown()


async def main():
    """CLI entry point."""
    config = TestConfig(
        base_url=os.getenv("TEST_BASE_URL", "http://localhost:5173"),
        test_email=os.getenv("TEST_EMAIL", "test@example.com"),
        test_password=os.getenv("TEST_PASSWORD", "testpassword123"),
        headless=os.getenv("TEST_HEADLESS", "true").lower() == "true",
    )
    
    agent = RouteCreatorTestAgent(config)
    results = await agent.run()
    
    # Exit with error code if any tests failed
    if any(not r["passed"] for r in results):
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())