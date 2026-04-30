def calculate_targets(
    weight_kg: float,
    height_cm: int,
    age: int,
    sex: str,
    goal: str,
) -> dict:
    if sex == "M":
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
    else:
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161

    tdee = bmr * 1.2

    adjustments = {"lose": -300, "maintain": 0, "gain": 300}
    target_calories = tdee + adjustments[goal]

    target_protein = (target_calories * 0.30) / 4
    target_carbs = (target_calories * 0.40) / 4
    target_fat = (target_calories * 0.30) / 9

    return {
        "target_calories": round(target_calories, 2),
        "target_protein": round(target_protein, 2),
        "target_carbs": round(target_carbs, 2),
        "target_fat": round(target_fat, 2),
    }
