"""Minimal, dependency-free logistic regression (full-batch gradient descent).

A handful of interpretable features and a few thousand training rows at most
(see ``recsys.model``) don't need numpy/scikit-learn. Keeping this pure
Python means the core ``recsys`` package adds zero new *required* runtime
dependency on top of ``pyproject.toml``'s existing fastapi/pydantic/uvicorn —
only the optional Kaggle calibration script pulls in heavier libraries.
"""

from __future__ import annotations

import math


def _dot(weights: list[float], features: list[float]) -> float:
    return sum(w * f for w, f in zip(weights, features))


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


class LogisticRegression:
    """Binary logistic regression with L2 regularization."""

    def __init__(self, n_features: int, *, learning_rate: float = 0.3, l2: float = 0.001):
        self.weights: list[float] = [0.0] * n_features
        self.bias: float = 0.0
        self.learning_rate = learning_rate
        self.l2 = l2

    def predict_proba(self, features: list[float]) -> float:
        return _sigmoid(_dot(self.weights, features) + self.bias)

    def fit(self, X: list[list[float]], y: list[float], *, epochs: int = 250) -> "LogisticRegression":
        n = len(X)
        if n == 0:
            return self
        for _ in range(epochs):
            grad_w = [0.0] * len(self.weights)
            grad_b = 0.0
            for features, label in zip(X, y):
                error = self.predict_proba(features) - label
                for i, f in enumerate(features):
                    grad_w[i] += error * f
                grad_b += error
            for i in range(len(self.weights)):
                self.weights[i] -= self.learning_rate * (grad_w[i] / n + self.l2 * self.weights[i])
            self.bias -= self.learning_rate * (grad_b / n)
        return self

    def feature_importance(self) -> list[float]:
        """Absolute weight per feature — used to sanity-check the fit is not degenerate."""
        return [abs(w) for w in self.weights]
