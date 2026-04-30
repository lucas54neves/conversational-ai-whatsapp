from nutrition_tools.calculator import calculate_targets


def test_male_maintain_matches_mifflin_st_jeor():
    # 80kg, 180cm, 30y, M, sedentary x1.2 → BMR=1780, TDEE=2136
    targets = calculate_targets(80, 180, 30, "M", "maintain")
    assert targets["target_calories"] == 2136
    # 30% protein at 4 kcal/g
    assert targets["target_protein"] == round(2136 * 0.30 / 4, 2)
    # 40% carbs at 4 kcal/g
    assert targets["target_carbs"] == round(2136 * 0.40 / 4, 2)
    # 30% fat at 9 kcal/g
    assert targets["target_fat"] == round(2136 * 0.30 / 9, 2)


def test_female_lose_subtracts_300():
    targets_maintain = calculate_targets(60, 165, 28, "F", "maintain")
    targets_lose = calculate_targets(60, 165, 28, "F", "lose")
    assert targets_lose["target_calories"] == targets_maintain["target_calories"] - 300


def test_male_gain_adds_300():
    targets_maintain = calculate_targets(70, 175, 25, "M", "maintain")
    targets_gain = calculate_targets(70, 175, 25, "M", "gain")
    assert targets_gain["target_calories"] == targets_maintain["target_calories"] + 300


def test_macro_split_sums_to_total_calories():
    targets = calculate_targets(75, 178, 32, "M", "maintain")
    macro_kcal = (
        targets["target_protein"] * 4 + targets["target_carbs"] * 4 + targets["target_fat"] * 9
    )
    assert abs(macro_kcal - targets["target_calories"]) < 1.0
