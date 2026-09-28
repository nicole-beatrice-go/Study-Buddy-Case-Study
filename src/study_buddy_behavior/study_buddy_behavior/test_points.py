# unused
# Filename: test_points.py
# Student:  Nicole Go, nbgo@ucsd.edu
# Group:    Study Buddy
# Project:  Study Buddy Pupper -- Point System Test (Final Project)
#
# Purpose:
#   Originally used to have a point system and test if we can add and subtract
#
# Why this exists:
#   To confirm that point additions, deductions,
#   and edge cases behaved as expected.
#
# Tests performed:
#   - Add points
#   - Remove points
#   - Verify returned values
#   - Verify point totals update correctly
#   - Test large deductions
#
#
# Usage:
#   python3 test_points.py
#
# Dependencies:
#   study_buddy_behavior.points.PointSystem
######################################################################## 

from study_buddy_behavior.points import PointSystem


def main():
    print("=== Point System Tests ===")

    points = PointSystem(start=50)

    print(f"Starting points: {points.points}")
    # test add points
    print("\nAdding 10 points...")
    result = points.add_points(10)
    print(f"Returned value: {result}")
    print(f"Current points: {points.points}")
    # test remove points
    print("\nRemoving 5 points...")
    result = points.remove_points(5)
    print(f"Returned value: {result}")
    print(f"Current points: {points.points}")

    print("\nAdding 25 points...")
    result = points.add_points(25)
    print(f"Returned value: {result}")
    print(f"Current points: {points.points}")

    print("\nRemoving 100 points...")
    result = points.remove_points(100)
    print(f"Returned value: {result}")
    print(f"Current points: {points.points}")

    print("\n=== Tests Complete ===")


if __name__ == "__main__":
    main()