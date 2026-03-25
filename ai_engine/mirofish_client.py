"""MiroFish async REST client module.

Provides:
- SwarmAssessment: dataclass for swarm simulation results
- parse_swarm_direction: extract BUY/SELL/NEUTRAL from German markdown report
- MiroFishCostLimiter: daily simulation count and token budget guard (MIRO-06)
- MiroFishClient: async REST client for MiroFish Flask backend
- run_simulation_loop: background asyncio task for periodic simulations
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


# =========================================================================
# SwarmAssessment
# =========================================================================


@dataclass
class SwarmAssessment:
    """Result of a MiroFish swarm simulation.

    Attributes:
        direction: Trading direction - "BUY", "SELL", or "NEUTRAL"
        confidence: Confidence score from 0.0 to 1.0
        reasoning: German text summary from the MiroFish report
        timestamp: Creation time (monotonic clock)
    """

    direction: str  # "BUY", "SELL", or "NEUTRAL"
    confidence: float  # 0.0 to 1.0
    reasoning: str  # German summary text from report
    timestamp: float = field(default_factory=time.monotonic)


# =========================================================================
# parse_swarm_direction
# =========================================================================

# German bullish keyword set -- economic factors driving gold higher
_BULLISH_KEYWORDS = {
    "aufwaertstrend",
    "steigende preise",
    "kaufsignal",
    "bullish",
    "preissteigerung",
    "hausse",
    "nachfrage steigt",
    "positive entwicklung",
    "zentralbank kauft",
    "geopolitische unsicherheit steigt",
    "inflationsdruck",
    "dollar schwaecht",
}

# German bearish keyword set -- economic factors pushing gold lower
_BEARISH_KEYWORDS = {
    "abwaertstrend",
    "fallende preise",
    "verkaufssignal",
    "bearish",
    "baisse",
    "kurs faellt",
    "dollar staerkt",
    "zinsanstieg",
    "restriktive geldpolitik",
    "druck auf goldpreis",
    "risikoappetit steigt",
}


def parse_swarm_direction(report_markdown: str) -> tuple[str, float, str]:
    """Parse a German MiroFish markdown report into (direction, confidence, reasoning).

    Args:
        report_markdown: Full markdown text from MiroFish report endpoint.

    Returns:
        Tuple of (direction, confidence, reasoning_summary) where:
        - direction: "BUY", "SELL", or "NEUTRAL"
        - confidence: float 0.0 to 1.0 (capped at 0.9)
        - reasoning_summary: brief text explanation
    """
    if not report_markdown or not report_markdown.strip():
        return ("NEUTRAL", 0.5, "Keine klare Richtung erkennbar")

    text_lower = report_markdown.lower()

    bullish_count = sum(1 for kw in _BULLISH_KEYWORDS if kw in text_lower)
    bearish_count = sum(1 for kw in _BEARISH_KEYWORDS if kw in text_lower)
    total = bullish_count + bearish_count

    if total == 0:
        return ("NEUTRAL", 0.5, "Keine klaren Schluesselwoerter gefunden")

    margin = abs(bullish_count - bearish_count)
    confidence = min(0.9, 0.5 + margin / (total * 2.0))

    # Build reasoning summary from first ~200 chars of markdown (non-empty lines)
    lines = [ln.strip() for ln in report_markdown.splitlines() if ln.strip()]
    summary = " ".join(lines[:3])[:200] if lines else report_markdown[:200]

    if bullish_count > bearish_count:
        direction = "BUY"
        reasoning = f"Bullische Signale ({bullish_count} vs {bearish_count}): {summary}"
    elif bearish_count > bullish_count:
        direction = "SELL"
        reasoning = f"Baerische Signale ({bearish_count} vs {bullish_count}): {summary}"
    else:
        direction = "NEUTRAL"
        confidence = 0.5
        reasoning = f"Ausgeglichene Signale ({bullish_count} bullisch, {bearish_count} baerissch): {summary}"

    return (direction, confidence, reasoning)


# =========================================================================
# MiroFishCostLimiter
# =========================================================================


class MiroFishCostLimiter:
    """Daily simulation counter and token budget guard.

    Tracks simulation count and token usage in a JSON file. Automatically
    resets counters on a new calendar day.

    MIRO-06: Limits simulations per day and enforces a daily token budget.
    """

    def __init__(
        self,
        state_file: str = "logs/mirofish_cost.json",
        max_sims_per_day: int = 48,
        token_budget_per_day: int = 200_000,
    ) -> None:
        self._state_file = state_file
        self._max_sims = max_sims_per_day
        self._token_budget = token_budget_per_day

    def _load(self) -> dict:
        """Load state from JSON file. Resets if date differs from today."""
        today = str(date.today())
        try:
            with open(self._state_file, "r") as f:
                state = json.load(f)
            if state.get("date") != today:
                return {"date": today, "sim_count": 0, "tokens_used": 0}
            return state
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {"date": today, "sim_count": 0, "tokens_used": 0}

    def _save(self, state: dict) -> None:
        """Write state dict to JSON file, creating parent dirs as needed."""
        Path(self._state_file).parent.mkdir(parents=True, exist_ok=True)
        with open(self._state_file, "w") as f:
            json.dump(state, f, indent=2)

    def can_run(self) -> tuple[bool, str]:
        """Check if another simulation is allowed.

        Returns:
            Tuple of (allowed, reason_string). If allowed, reason is empty string.
        """
        state = self._load()
        if state["sim_count"] >= self._max_sims:
            return (False, f"Tageslimit erreicht: {state['sim_count']}/{self._max_sims} Simulationen")
        if state["tokens_used"] >= self._token_budget:
            return (
                False,
                f"Token-Budget erschoepft: {state['tokens_used']}/{self._token_budget} Tokens",
            )
        return (True, "")

    def record_run(self, tokens_used: int = 5000) -> None:
        """Record a completed simulation run.

        Increments sim_count by 1 and tokens_used by tokens_used argument.
        """
        state = self._load()
        state["sim_count"] += 1
        state["tokens_used"] += tokens_used
        self._save(state)


# =========================================================================
# MiroFishClient
# =========================================================================


class MiroFishClient:
    """Async REST client for the MiroFish Flask backend.

    Manages the full simulation pipeline:
    - One-time graph setup (ontology + build)
    - Per-simulation pipeline (create -> prepare -> start -> report)
    - Result caching with configurable TTL (D-11)
    - Daily cost limiting (MIRO-06)
    - Graceful degradation when backend is unavailable (D-16/D-18)
    """

    def __init__(
        self,
        base_url: str = "http://localhost:5001",
        timeout_seconds: float = 180.0,
        cache_ttl_seconds: float = 360.0,
        max_simulations_per_day: int = 48,
        token_budget_per_day: int = 200_000,
        max_rounds: int = 15,
        seed_dir: str = "mirofish_seeds",
        state_file: str = "logs/mirofish_state.json",
        cost_file: str = "logs/mirofish_cost.json",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._cache_ttl = cache_ttl_seconds
        self._max_rounds = max_rounds
        self._seed_dir = seed_dir
        self._state_file = state_file

        self._cached: Optional[SwarmAssessment] = None
        self._offline_warned: bool = False
        self._project_id: Optional[str] = None
        self._graph_id: Optional[str] = None

        self._cost_limiter = MiroFishCostLimiter(
            state_file=cost_file,
            max_sims_per_day=max_simulations_per_day,
            token_budget_per_day=token_budget_per_day,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        """Check if MiroFish backend is reachable.

        Returns:
            True if backend responds with HTTP 200, False otherwise.
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/health")
                return resp.status_code == 200
        except Exception:
            return False

    def get_cached_assessment(self) -> Optional[SwarmAssessment]:
        """Return cached SwarmAssessment if still within TTL.

        Returns:
            SwarmAssessment if age < cache_ttl_seconds, else None.
        """
        if self._cached is None:
            return None
        age = time.monotonic() - self._cached.timestamp
        if age > self._cache_ttl:
            return None
        return self._cached

    def check_veto(self, signal: dict) -> dict:
        """Apply MiroFish veto check to an ML signal (D-06 to D-09).

        Logic:
        - If no cached assessment: return signal unchanged (D-16)
        - If swarm agrees or is NEUTRAL: return signal with mirofish metadata
        - If swarm contradicts (BUY vs SELL): convert to HOLD with veto reason (D-09)

        Args:
            signal: ML signal dict with at least {"action": "BUY"|"SELL"|"HOLD"}

        Returns:
            Modified signal dict with mirofish_veto and metadata fields.
        """
        assessment = self.get_cached_assessment()
        if assessment is None:
            return signal  # No cache -- trade without MiroFish (D-16)

        ml_action = signal.get("action", "HOLD")
        swarm_direction = assessment.direction

        # Veto: swarm directly contradicts ML signal
        if (
            (ml_action == "BUY" and swarm_direction == "SELL")
            or (ml_action == "SELL" and swarm_direction == "BUY")
        ):
            veto_reason = (
                f"MiroFish Veto: Schwarm={swarm_direction}, ML={ml_action}. "
                f"{assessment.reasoning}"
            )
            logger.info("Trade BLOCKED by MiroFish: %s", veto_reason)
            return {
                **signal,
                "action": "HOLD",
                "mirofish_veto": True,
                "mirofish_reasoning": veto_reason,
            }

        # Agreement or neutral -- trade proceeds
        return {
            **signal,
            "mirofish_veto": False,
            "mirofish_direction": swarm_direction,
            "mirofish_confidence": assessment.confidence,
            "mirofish_reasoning": assessment.reasoning,
        }

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _load_state(self) -> None:
        """Load project_id and graph_id from state JSON file."""
        try:
            with open(self._state_file, "r") as f:
                state = json.load(f)
            self._project_id = state.get("project_id")
            self._graph_id = state.get("graph_id")
            logger.debug(
                "MiroFish state loaded: project_id=%s, graph_id=%s",
                self._project_id,
                self._graph_id,
            )
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            self._project_id = None
            self._graph_id = None

    def _save_state(self) -> None:
        """Persist project_id and graph_id to state JSON file."""
        Path(self._state_file).parent.mkdir(parents=True, exist_ok=True)
        state = {
            "project_id": self._project_id,
            "graph_id": self._graph_id,
        }
        with open(self._state_file, "w") as f:
            json.dump(state, f, indent=2)
        logger.debug("MiroFish state saved: %s", state)

    # ------------------------------------------------------------------
    # Graph setup (one-time)
    # ------------------------------------------------------------------

    async def _ensure_graph(self) -> None:
        """Ensure project_id and graph_id are available, building graph if needed."""
        if self._project_id and self._graph_id:
            return

        # Try loading from persisted state first
        self._load_state()
        if self._project_id and self._graph_id:
            return

        # No persisted state -- build graph from scratch
        await self._build_graph()

    async def _build_graph(self) -> None:
        """Run the full one-time graph construction sequence.

        Steps:
        1. Read seed .md files from seed_dir
        2. POST /api/graph/ontology/generate
        3. POST /api/graph/build
        4. Poll GET /api/graph/task/{task_id} until completed
        5. Save project_id + graph_id to state file
        """
        logger.info("MiroFish: Building knowledge graph from seed files in '%s'", self._seed_dir)

        # Gather seed files
        seed_files = []
        seed_path = Path(self._seed_dir)
        if seed_path.exists():
            for md_file in sorted(seed_path.glob("*.md")):
                content = md_file.read_text(encoding="utf-8")
                seed_files.append({"name": md_file.name, "content": content})

        if not seed_files:
            logger.warning("MiroFish: No seed files found in '%s' -- using empty ontology", self._seed_dir)

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            # Step 1: Generate ontology
            resp = await client.post(
                f"{self._base_url}/api/graph/ontology/generate",
                json={
                    "files": seed_files,
                    "requirements": "Gold market analysis for XAUUSD trading",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            project_id = data.get("project_id") or data.get("data", {}).get("project_id")
            self._project_id = project_id
            logger.info("MiroFish: Ontology generated, project_id=%s", project_id)

            # Step 2: Build graph
            resp = await client.post(
                f"{self._base_url}/api/graph/build",
                json={"project_id": project_id},
            )
            resp.raise_for_status()
            data = resp.json()
            task_id = data.get("task_id") or data.get("data", {}).get("task_id")

            # Step 3: Poll until completed
            while True:
                await asyncio.sleep(3)
                resp = await client.get(f"{self._base_url}/api/graph/task/{task_id}")
                resp.raise_for_status()
                data = resp.json()
                task_data = data.get("data", data)
                status = task_data.get("status")
                if status == "completed":
                    self._graph_id = task_data.get("graph_id")
                    logger.info("MiroFish: Graph built, graph_id=%s", self._graph_id)
                    break
                elif status == "failed":
                    raise RuntimeError(f"MiroFish graph build failed: {task_data}")
                logger.debug("MiroFish: Graph task status=%s, waiting...", status)

        self._save_state()

    # ------------------------------------------------------------------
    # Per-simulation pipeline
    # ------------------------------------------------------------------

    async def _run_one_simulation(self) -> None:
        """Execute the full per-simulation pipeline.

        Steps:
        1. Ensure graph is built
        2. Create simulation
        3. Prepare profiles
        4. Prepare config
        5. Start simulation
        6. Poll run-status until completed
        7. Generate report
        8. Parse report markdown -> SwarmAssessment
        9. Record cost
        """
        try:
            await self._ensure_graph()

            async with httpx.AsyncClient(timeout=self._timeout) as client:
                # Step 1: Create simulation
                resp = await client.post(
                    f"{self._base_url}/api/simulation/create",
                    json={
                        "project_id": self._project_id,
                        "graph_id": self._graph_id,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                sim_id = data.get("simulation_id") or data.get("data", {}).get("simulation_id")
                logger.info("MiroFish: Simulation created, id=%s", sim_id)

                # Step 2: Prepare profiles
                resp = await client.post(
                    f"{self._base_url}/api/simulation/prepare",
                    json={"simulation_id": sim_id, "type": "profiles"},
                )
                resp.raise_for_status()
                await self._poll_prepare_status(client, sim_id, "profiles")

                # Step 3: Prepare config
                resp = await client.post(
                    f"{self._base_url}/api/simulation/prepare",
                    json={"simulation_id": sim_id, "type": "config"},
                )
                resp.raise_for_status()
                await self._poll_prepare_status(client, sim_id, "config")

                # Step 4: Start simulation
                resp = await client.post(
                    f"{self._base_url}/api/simulation/start",
                    json={
                        "simulation_id": sim_id,
                        "platform": "parallel",
                        "max_rounds": self._max_rounds,
                        "enable_graph_memory_update": False,
                    },
                )
                resp.raise_for_status()

                # Step 5: Poll run-status
                while True:
                    await asyncio.sleep(3)
                    resp = await client.get(f"{self._base_url}/api/simulation/{sim_id}/run-status")
                    resp.raise_for_status()
                    data = resp.json()
                    run_data = data.get("data", data)
                    status = run_data.get("status")
                    if status == "completed":
                        logger.info("MiroFish: Simulation completed, id=%s", sim_id)
                        break
                    elif status == "failed":
                        raise RuntimeError(f"MiroFish simulation failed: {run_data}")
                    logger.debug("MiroFish: Simulation status=%s, waiting...", status)

                # Step 6: Generate report
                resp = await client.post(
                    f"{self._base_url}/api/report/generate",
                    json={"simulation_id": sim_id},
                )
                resp.raise_for_status()
                report_id = await self._poll_report_status(client, sim_id)

                # Step 7: Fetch report
                resp = await client.get(f"{self._base_url}/api/report/{report_id}")
                resp.raise_for_status()
                data = resp.json()
                markdown_content = data.get("data", {}).get("content", "")

                # Step 8: Parse direction and create assessment
                direction, confidence, reasoning = parse_swarm_direction(markdown_content)
                self._cached = SwarmAssessment(
                    direction=direction,
                    confidence=confidence,
                    reasoning=reasoning,
                )
                logger.info(
                    "MiroFish: Assessment stored -- direction=%s, confidence=%.2f",
                    direction,
                    confidence,
                )

            # Step 9: Record cost (estimate ~5000 tokens per simulation)
            estimated_tokens = 5000
            self._cost_limiter.record_run(tokens_used=estimated_tokens)

        except Exception as exc:
            # Non-fatal: log warning, do not re-raise (D-16)
            logger.warning("MiroFish simulation failed (non-fatal): %s", exc)

    async def _poll_prepare_status(
        self, client: httpx.AsyncClient, sim_id: str, prepare_type: str
    ) -> None:
        """Poll /api/simulation/prepare/status until preparation is done."""
        while True:
            await asyncio.sleep(3)
            resp = await client.post(
                f"{self._base_url}/api/simulation/prepare/status",
                json={"simulation_id": sim_id, "type": prepare_type},
            )
            resp.raise_for_status()
            data = resp.json()
            status_data = data.get("data", data)
            status = status_data.get("status")
            if status in ("completed", "done", "ready"):
                logger.debug("MiroFish: Prepare '%s' done for sim=%s", prepare_type, sim_id)
                return
            elif status == "failed":
                raise RuntimeError(f"MiroFish prepare '{prepare_type}' failed: {status_data}")
            logger.debug(
                "MiroFish: Prepare '%s' status=%s, waiting...", prepare_type, status
            )

    async def _poll_report_status(
        self, client: httpx.AsyncClient, sim_id: str
    ) -> str:
        """Poll /api/report/generate/status until report is ready; return report_id."""
        while True:
            await asyncio.sleep(3)
            resp = await client.post(
                f"{self._base_url}/api/report/generate/status",
                json={"simulation_id": sim_id},
            )
            resp.raise_for_status()
            data = resp.json()
            report_data = data.get("data", data)
            status = report_data.get("status")
            if status in ("completed", "done", "ready"):
                report_id = report_data.get("report_id")
                logger.debug("MiroFish: Report ready, report_id=%s", report_id)
                return report_id
            elif status == "failed":
                raise RuntimeError(f"MiroFish report generation failed: {report_data}")
            logger.debug("MiroFish: Report status=%s, waiting...", status)


# =========================================================================
# Background simulation loop
# =========================================================================


async def run_simulation_loop(
    client: MiroFishClient,
    interval_seconds: int = 300,
) -> None:
    """Background asyncio task: run simulations periodically.

    - Checks health every interval; logs one offline warning (D-17)
    - Checks cost limits before running simulation (MIRO-06)
    - Sleeps interval_seconds between iterations
    - Re-raises CancelledError for clean shutdown
    - Catches all other exceptions to keep loop alive (D-18)

    Args:
        client: MiroFishClient instance to use for simulations.
        interval_seconds: Time between simulation attempts.
    """
    logger.info("MiroFish simulation loop started (interval=%ds)", interval_seconds)

    while True:
        try:
            is_alive = await client.health_check()

            if not is_alive:
                if not client._offline_warned:
                    logger.warning(
                        "MiroFish backend nicht erreichbar -- Bot handelt ohne Schwarmintelligenz"
                    )
                    client._offline_warned = True
            else:
                client._offline_warned = False
                allowed, reason = client._cost_limiter.can_run()
                if allowed:
                    await client._run_one_simulation()
                else:
                    logger.debug("MiroFish simulation skipped: %s", reason)

            await asyncio.sleep(interval_seconds)

        except asyncio.CancelledError:
            logger.info("MiroFish simulation loop cancelled -- shutting down")
            raise

        except Exception as exc:
            logger.debug("MiroFish simulation loop error (continuing): %s", exc)
            await asyncio.sleep(interval_seconds)
