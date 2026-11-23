"""Benchmark b01: small arithmetic / branching functions."""


def clamp(value: int, low: int, high: int) -> int:
    if low > high:
        raise ValueError("low must not exceed high")
    if value < low:
        return low
    if value > high:
        return high
    return value


def sign(n: int) -> int:
    if n < 0:
        return -1
    elif n == 0:
        return 0
    return 1


def safe_divide(a: float, b: float) -> float:
    if b == 0:
        raise ZeroDivisionError("division by zero")
    return a / b


def grade(score: int) -> str:
    if score < 0 or score > 100:
        raise ValueError("score out of range")
    if score >= 90:
        return "A"
    elif score >= 75:
        return "B"
    elif score >= 50:
        return "C"
    return "F"


def is_even(n: int) -> bool:
    return n % 2 == 0


class Counter:
    def __init__(self, start: int = 0):
        self.value = start

    def add(self, amount: int) -> int:
        if amount < 0:
            raise ValueError("amount must be non-negative")
        self.value += amount
        return self.value
