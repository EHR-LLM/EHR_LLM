"""
Deterministic Score Calculator (MELD, FIB-4, Child-Pugh).
Used by MedAgentBench to ensure accurate score computation.
Available for both calculator and no-calculator modes.
"""

import math


def calculate_meld(bilirubin_raw: float, inr_raw: float, creatinine_raw: float) -> dict:
    """
    Calculate MELD score with proper correction logic.
    
    Correction rules:
    - If raw value < 1: use 1.0, corrected = true
    - If raw value >= 1: use raw value, corrected = false
    
    MELD formula (using natural logarithm):
    MELD = 3.78 * ln(bilirubin_used) + 11.2 * ln(inr_used) + 9.57 * ln(creatinine_used) + 6.43
    
    Args:
        bilirubin_raw: Raw bilirubin value
        inr_raw: Raw INR value
        creatinine_raw: Raw creatinine value
    
    Returns:
        dict with all computed fields
    """
    # Calculate used values (apply correction)
    if bilirubin_raw < 1:
        bilirubin_used = 1.0
        bilirubin_corrected = True
    else:
        bilirubin_used = bilirubin_raw
        bilirubin_corrected = False
    
    if inr_raw < 1:
        inr_used = 1.0
        inr_corrected = True
    else:
        inr_used = inr_raw
        inr_corrected = False
    
    if creatinine_raw < 1:
        creatinine_used = 1.0
        creatinine_corrected = True
    else:
        creatinine_used = creatinine_raw
        creatinine_corrected = False
    
    # Calculate MELD using natural logarithm
    meld_score = (
        3.78 * math.log(bilirubin_used) +
        11.2 * math.log(inr_used) +
        9.57 * math.log(creatinine_used) +
        6.43
    )
    
    # Round to 2 decimal places
    meld_score = round(meld_score, 2)
    
    return {
        "bilirubin_used": bilirubin_used,
        "inr_used": inr_used,
        "creatinine_used": creatinine_used,
        "bilirubin_corrected": bilirubin_corrected,
        "inr_corrected": inr_corrected,
        "creatinine_corrected": creatinine_corrected,
        "meld_score": meld_score
    }


def calculate_fib4(age: int, ast_raw: float, alt_raw: float, platelets_raw: float) -> dict:
    """
    Calculate FIB-4 score.
    
    FIB-4 formula: (Age × AST) / (Platelets × sqrt(ALT))
    
    Args:
        age: Patient age in years
        ast_raw: Raw AST value
        alt_raw: Raw ALT value
        platelets_raw: Raw platelet count
    
    Returns:
        dict with computed FIB-4 score
    """
    # Calculate square root of ALT
    alt_sqrt = math.sqrt(alt_raw) if alt_raw > 0 else 0
    
    # Calculate FIB-4
    if platelets_raw > 0 and alt_sqrt > 0:
        fib4_score = (age * ast_raw) / (platelets_raw * alt_sqrt)
    else:
        fib4_score = 0.0
    
    # Round to 2 decimal places
    fib4_score = round(fib4_score, 2)
    
    return {
        "age": age,
        "ast_raw": ast_raw,
        "alt_raw": alt_raw,
        "platelets_raw": platelets_raw,
        "fib4_score": fib4_score
    }


def calculate_child_pugh(bilirubin_raw: float, albumin_raw: float, inr_raw: float,
                         ascites_present: bool = False, encephalopathy_present: bool = False) -> dict:
    """
    Calculate Child-Pugh score.
    
    Point system:
    - Bilirubin: <2 = 1pt, 2-3 = 2pts, >3 = 3pts
    - Albumin: >3.5 = 1pt, 2.8-3.5 = 2pts, <2.8 = 3pts
    - INR: <1.7 = 1pt, 1.7-2.3 = 2pts, >2.3 = 3pts
    - Ascites: None = 1pt, Present = 2pts
    - Encephalopathy: None = 1pt, Present = 2pts
    
    Args:
        bilirubin_raw: Raw bilirubin value (mg/dL)
        albumin_raw: Raw albumin value (g/dL)
        inr_raw: Raw INR value
        ascites_present: Whether ascites is present (same-day Condition evidence)
        encephalopathy_present: Whether encephalopathy is present (same-day Condition evidence)
    
    Returns:
        dict with point breakdown and total Child-Pugh score
    """
    # Bilirubin points
    if bilirubin_raw < 2:
        bilirubin_points = 1
    elif bilirubin_raw <= 3:
        bilirubin_points = 2
    else:
        bilirubin_points = 3
    
    # Albumin points
    if albumin_raw > 3.5:
        albumin_points = 1
    elif albumin_raw >= 2.8:
        albumin_points = 2
    else:
        albumin_points = 3
    
    # INR points
    if inr_raw < 1.7:
        inr_points = 1
    elif inr_raw <= 2.3:
        inr_points = 2
    else:
        inr_points = 3
    
    # Ascites points (presence = 2pts, absence = 1pt)
    ascites_points = 2 if ascites_present else 1
    
    # Encephalopathy points (presence = 2pts, absence = 1pt)
    encephalopathy_points = 2 if encephalopathy_present else 1
    
    # Total score
    child_pugh_score = bilirubin_points + albumin_points + inr_points + ascites_points + encephalopathy_points
    
    return {
        "bilirubin_raw": bilirubin_raw,
        "albumin_raw": albumin_raw,
        "inr_raw": inr_raw,
        "ascites_present_same_day": ascites_present,
        "encephalopathy_present_same_day": encephalopathy_present,
        "bilirubin_points": bilirubin_points,
        "albumin_points": albumin_points,
        "inr_points": inr_points,
        "ascites_points": ascites_points,
        "encephalopathy_points": encephalopathy_points,
        "child_pugh_score": child_pugh_score
    }


def test_calculate_meld():
    """Test cases to verify MELD calculator correctness."""
    # Test case 1: All values >= 1 (no correction)
    result = calculate_meld(2.0, 1.5, 1.2)
    assert result["bilirubin_used"] == 2.0
    assert result["bilirubin_corrected"] == False
    assert result["inr_used"] == 1.5
    assert result["inr_corrected"] == False
    assert result["creatinine_used"] == 1.2
    assert result["creatinine_corrected"] == False
    
    # Test case 2: All values < 1 (correction applied)
    result = calculate_meld(0.4, 0.8, 0.58)
    assert result["bilirubin_used"] == 1.0
    assert result["bilirubin_corrected"] == True
    assert result["inr_used"] == 1.0
    assert result["inr_corrected"] == True
    assert result["creatinine_used"] == 1.0
    assert result["creatinine_corrected"] == True
    # Expected meld_score: 3.78*0 + 11.2*0 + 9.57*0 + 6.43 = 6.43
    assert result["meld_score"] == 6.43
    
    # Test case 3: Exact 1.0 is NOT corrected
    result = calculate_meld(1.0, 1.0, 1.0)
    assert result["bilirubin_used"] == 1.0
    assert result["bilirubin_corrected"] == False
    assert result["inr_used"] == 1.0
    assert result["inr_corrected"] == False
    assert result["creatinine_used"] == 1.0
    assert result["creatinine_corrected"] == False
    
    print("MELD calculator tests passed!")


def test_calculate_fib4():
    """Test cases to verify FIB-4 calculator correctness."""
    # Test case: typical values
    # FIB-4 = (71 * 189) / (164 * sqrt(137)) = 13419 / (164 * 11.70) = 13419 / 1919.88 = 6.99
    result = calculate_fib4(71, 189, 137, 164)
    assert result["age"] == 71
    assert result["ast_raw"] == 189
    assert result["alt_raw"] == 137
    assert result["platelets_raw"] == 164
    assert abs(result["fib4_score"] - 6.99) < 0.01
    
    print("FIB-4 calculator tests passed!")


def test_calculate_child_pugh():
    """Test cases to verify Child-Pugh calculator correctness."""
    # Test case: no ascites, no encephalopathy, normal labs
    result = calculate_child_pugh(1.5, 3.6, 1.2, False, False)
    assert result["bilirubin_points"] == 1  # < 2
    assert result["albumin_points"] == 1  # > 3.5
    assert result["inr_points"] == 1  # < 1.7
    assert result["ascites_points"] == 1  # absent
    assert result["encephalopathy_points"] == 1  # absent
    assert result["child_pugh_score"] == 5
    
    # Test case: with ascites, with encephalopathy, high labs
    result = calculate_child_pugh(5.0, 2.5, 2.0, True, True)
    assert result["bilirubin_points"] == 3  # > 3
    assert result["albumin_points"] == 3  # < 2.8
    assert result["inr_points"] == 2  # 1.7-2.3
    assert result["ascites_points"] == 2  # present
    assert result["encephalopathy_points"] == 2  # present
    assert result["child_pugh_score"] == 12
    
    print("Child-Pugh calculator tests passed!")


if __name__ == "__main__":
    test_calculate_meld()
    test_calculate_fib4()
    test_calculate_child_pugh()
    print("All calculator tests passed!")