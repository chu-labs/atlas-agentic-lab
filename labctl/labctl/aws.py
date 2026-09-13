"""Thin boto3 session helpers."""
from __future__ import annotations

from functools import lru_cache

import boto3

from .config import AWS_PROFILE, AWS_REGION


@lru_cache
def session() -> boto3.Session:
    return boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)


def client(name: str):
    return session().client(name)
