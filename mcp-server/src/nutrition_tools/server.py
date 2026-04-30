import os

import uvicorn
from mcp.server.fastmcp import FastMCP

from . import db
from . import tools as t

mcp = FastMCP("nutrition-tools")


@mcp.tool()
def search_food(query: str) -> list[dict]:
    """Search for foods in the TACO Brazilian food database.

    Returns up to 5 candidates with name and macros per 100g.
    Use the returned food id when calling save_meal.
    """
    return t.search_food(query)


@mcp.tool()
def save_user_profile(
    phone: str,
    weight_kg: float,
    height_cm: int,
    age: int,
    sex: str,
    goal: str,
) -> dict:
    """Save or update a user profile and calculate daily macro targets.

    sex must be 'M' or 'F'.
    goal must be 'lose', 'maintain', or 'gain'.
    Targets are calculated via Mifflin-St Jeor with sedentary activity factor (x1.2).
    """
    return t.save_user_profile(phone, weight_kg, height_cm, age, sex, goal)


@mcp.tool()
def get_user_profile(phone: str) -> dict | None:
    """Retrieve a user profile and daily targets.

    Returns None when the user has no profile — this must trigger the onboarding flow.
    """
    return t.get_user_profile(phone)


@mcp.tool()
def save_meals(phone: str, items: list[dict]) -> list[dict]:
    """Log one or more meals atomically for a user.

    Each item must contain `food_name`, `taco_food_id`, and `quantity_g`.
    All inserts share a single transaction — if any food id is invalid,
    nothing is committed. Calories and macros are calculated proportionally
    from the TACO per-100g values. Only call this after the user has
    confirmed the meal summary.
    """
    return t.save_meals(phone, items)


@mcp.tool()
def get_daily_summary(phone: str, date: str | None = None) -> dict | None:
    """Get a user's daily meal totals vs. targets.

    date format: YYYY-MM-DD. Defaults to today when omitted.
    Returns consumed amounts, targets, and percentage progress per macro.
    Returns None when the user has no profile — route to onboarding.
    """
    return t.get_daily_summary(phone, date)


@mcp.tool()
def get_weekly_history(phone: str) -> list[dict] | None:
    """Get the last 7 days of daily summaries for a user.

    Returns daily totals for calories and macros for each of the past 7 days.
    Returns None when the user has no profile — route to onboarding.
    """
    return t.get_weekly_history(phone)


def main() -> None:
    db.init_pool()
    uvicorn.run(
        mcp.sse_app(),
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
    )


if __name__ == "__main__":
    main()
