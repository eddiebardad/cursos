"""Sequential execution and fallback policy for provider strategies."""

from __future__ import annotations

from urllib.parse import urlsplit

from core.drivers import run_driver
from core.exceptions import (
    HTTPStatusError,
    NetworkError,
    ParsingError,
    QualityGateError,
    UpstreamFormatError,
    WAFChallengeError,
)
from core.manifest import ProviderDefinition, StrategyDefinition, load_provider_manifest
from core.quality import BatchQualityGate
from schemas.models import Course
from utils.logger import get_logger

logger = get_logger(__name__)


class StrategyRunner:
    def __init__(
        self,
        manifest: dict[str, ProviderDefinition] | None = None,
    ) -> None:
        self.manifest = manifest if manifest is not None else load_provider_manifest()

    def run(
        self,
        provider_id: str,
        adapter: object,
        url: str,
        *,
        limit: int = 0,
        enable_modules: bool = False,
    ) -> list[Course]:
        provider = self.manifest[provider_id]
        blocked_hosts: set[str] = set()
        last_error: Exception | None = None
        enrichment_fallback: list[Course] | None = None
        strategies = provider.strategies

        for index, strategy in enumerate(strategies):
            target_host = self._strategy_host(provider, strategy)
            if target_host in blocked_hosts:
                logger.warning(
                    "StrategyRunner skipped provider=%s driver=%s host=%s reason=waf_blocked",
                    provider_id,
                    strategy.driver,
                    target_host,
                )
                continue

            try:
                raw_courses = run_driver(
                    strategy.driver,
                    adapter,
                    url,
                    provider,
                    strategy.params,
                    limit,
                    enable_modules,
                )
                normalized_courses = [
                    Course.model_validate(
                        {
                            **course.model_dump(),
                            "provider": course.provider or provider.name,
                            "in_language": course.in_language or provider.default_language,
                        }
                    )
                    for course in raw_courses
                ]
                courses = BatchQualityGate.validate(normalized_courses, provider)
            except HTTPStatusError as exc:
                last_error = exc
                if exc.waf_blocked and exc.host:
                    blocked_hosts.add(exc.host)
                self._warn(provider_id, strategy, exc)
                continue
            except WAFChallengeError as exc:
                last_error = exc
                if exc.host:
                    blocked_hosts.add(exc.host)
                self._warn(provider_id, strategy, exc)
                continue
            except (NetworkError, UpstreamFormatError, ParsingError, QualityGateError) as exc:
                last_error = exc
                self._warn(provider_id, strategy, exc)
                continue

            if not courses:
                logger.warning(
                    "StrategyRunner warning provider=%s driver=%s reason=zero_courses",
                    provider_id,
                    strategy.driver,
                )
                continue

            if (
                len(courses) >= 5
                and all(not course.description for course in courses)
                and index + 1 < len(strategies)
            ):
                enrichment_fallback = courses
                logger.warning(
                    "StrategyRunner warning provider=%s driver=%s "
                    "reason=description_enrichment_fallback",
                    provider_id,
                    strategy.driver,
                )
                continue

            if enrichment_fallback is not None:
                return self._merge_enrichment(enrichment_fallback, courses)
            return courses

        if enrichment_fallback is not None:
            return enrichment_fallback
        if last_error is not None:
            raise last_error
        return []

    @staticmethod
    def _strategy_host(
        provider: ProviderDefinition,
        strategy: StrategyDefinition,
    ) -> str:
        target = (
            strategy.params.get("url")
            or strategy.params.get("sitemap_url")
            or strategy.params.get("host")
            or provider.base_url
        )
        target_text = str(target)
        if "://" not in target_text:
            target_text = f"https://{target_text}"
        return (urlsplit(target_text).hostname or "").casefold()

    @staticmethod
    def _warn(
        provider_id: str,
        strategy: StrategyDefinition,
        exc: Exception,
    ) -> None:
        logger.warning(
            "StrategyRunner warning provider=%s driver=%s error=%s",
            provider_id,
            strategy.driver,
            exc,
        )

    @staticmethod
    def _merge_enrichment(
        original: list[Course],
        enriched: list[Course],
    ) -> list[Course]:
        enriched_by_url = {course.canonical_url: course for course in enriched}
        merged: list[Course] = []
        for course in original:
            additional = enriched_by_url.get(course.canonical_url)
            if additional and additional.description:
                merged.append(
                    Course.model_validate(
                        {
                            **course.model_dump(),
                            "description": additional.description,
                        }
                    )
                )
            else:
                merged.append(course)
        known_urls = {course.canonical_url for course in merged}
        for course in enriched:
            if course.canonical_url not in known_urls:
                merged.append(course)
                known_urls.add(course.canonical_url)
        return merged
