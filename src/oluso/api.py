from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings, get_settings
from .schemas import (
    AccountCreate,
    AccountResponse,
    AppealRequest,
    AuditVerificationResponse,
    BehaviorEventIn,
    ConsortiumReportRequest,
    FeedbackRequest,
    FraudSketchIndicatorType,
    FraudSketchReportRequest,
    FraudSketchRevocationRequest,
    LifecycleTransitionRequest,
    MetricsResponse,
    OutageHeartbeatRequest,
    OutageSimulationRequest,
    PolicySimulationRequest,
    PrivacyRequest,
    ProfileResponse,
    ProfileSuccessionRequest,
    ReconciliationRequest,
    RiskDecisionResponse,
)
from .security import SlidingWindowRateLimiter
from .service import AtoService, ConflictError, NotFoundError


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or get_settings()
    service = AtoService(runtime_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        service.close()

    application = FastAPI(
        lifespan=lifespan,
        title="Oluso Account Takeover API",
        version="1.4.0",
        description=(
            "Explainable behavioural account-takeover scoring for app and USSD events, "
            "with reversible policy responses and a Regret Budget."
        ),
    )
    application.state.service = service
    application.state.settings = runtime_settings
    application.add_middleware(
        CORSMiddleware,
        allow_origins=runtime_settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-API-Key", "X-Tenant-ID"],
    )

    limiter = SlidingWindowRateLimiter(runtime_settings.request_rate_per_minute)

    @application.middleware("http")
    async def security_controls(request: Request, call_next):
        if request.headers.get("content-length") and int(request.headers["content-length"]) > runtime_settings.max_request_bytes:
            return Response(status_code=413, content="request too large")
        identity = request.headers.get("x-api-key", request.client.host if request.client else "unknown")
        if not limiter.allow(identity):
            return Response(status_code=429, content="rate limit exceeded")
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def require_role(*allowed_roles: str):
        def dependency(
            x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
        ) -> None:
            roles = {
                runtime_settings.api_key: "integration",
                runtime_settings.analyst_api_key: "analyst",
                runtime_settings.auditor_api_key: "auditor",
                runtime_settings.admin_api_key: "admin",
            }
            role = roles.get(x_api_key or "")
            if role is None:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API key")
            if role not in allowed_roles and role != "admin":
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient role")
        return dependency

    def tenant_id(x_tenant_id: Annotated[str, Header(alias="X-Tenant-ID")] = "default") -> str:
        if x_tenant_id not in runtime_settings.allowed_tenants:
            raise HTTPException(status_code=403, detail="tenant not allowed")
        return x_tenant_id

    integration = [Depends(require_role("integration", "analyst", "auditor"))]
    analyst = [Depends(require_role("analyst"))]
    auditor = [Depends(require_role("auditor"))]
    admin = [Depends(require_role("admin"))]

    def translate_error(exc: Exception) -> HTTPException:
        if isinstance(exc, NotFoundError):
            return HTTPException(status_code=404, detail=str(exc))
        if isinstance(exc, ConflictError):
            return HTTPException(status_code=409, detail=str(exc))
        return HTTPException(status_code=500, detail="internal service error")

    @application.get("/health")
    def health() -> dict[str, Any]:
        audit_status = service.audit.verify()
        resilience = service.resilience_status("default")
        return {
            "status": (
                "ok"
                if audit_status["valid"] and resilience["mode"] == "online"
                else "degraded"
            ),
            "environment": runtime_settings.environment,
            "model_available": service.model_bundle.available,
            "model_version": service.model_bundle.version,
            "model_inference_path": service.model_bundle.inference_path,
            "audit_chain_valid": audit_status["valid"],
            "resilience_mode": resilience["mode"],
        }

    @application.post(
        "/v1/accounts",
        response_model=AccountResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=integration,
    )
    def create_account(request: AccountCreate, tenant: str = Depends(tenant_id)) -> AccountResponse:
        try:
            return service.create_account(request, tenant)
        except (NotFoundError, ConflictError) as exc:
            raise translate_error(exc) from exc

    @application.get(
        "/v1/accounts/{account_id}/profile",
        response_model=ProfileResponse,
        dependencies=integration,
    )
    def get_profile(account_id: str, tenant: str = Depends(tenant_id)) -> ProfileResponse:
        try:
            return service.get_profile(account_id, tenant)
        except NotFoundError as exc:
            raise translate_error(exc) from exc

    @application.post(
        "/v1/events/score",
        response_model=RiskDecisionResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=integration,
    )
    def score_event(event: BehaviorEventIn, tenant: str = Depends(tenant_id)) -> RiskDecisionResponse:
        try:
            return service.score_event(event, tenant)
        except (NotFoundError, ConflictError) as exc:
            raise translate_error(exc) from exc

    @application.get(
        "/v1/accounts/{account_id}/decisions",
        response_model=list[RiskDecisionResponse],
        dependencies=integration,
    )
    def get_decisions(
        account_id: str,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        tenant: str = Depends(tenant_id),
    ) -> list[RiskDecisionResponse]:
        try:
            return service.get_decisions(account_id, limit, tenant)
        except NotFoundError as exc:
            raise translate_error(exc) from exc

    @application.post(
        "/v1/decisions/{decision_id}/feedback",
        dependencies=analyst,
    )
    def add_feedback(decision_id: str, request: FeedbackRequest, tenant: str = Depends(tenant_id)) -> dict[str, Any]:
        try:
            return service.add_feedback(decision_id, request, tenant)
        except (NotFoundError, ConflictError) as exc:
            raise translate_error(exc) from exc

    @application.get(
        "/v1/agent-terminals/{terminal_token}/status",
        dependencies=analyst,
    )
    def agent_terminal_status(
        terminal_token: str,
        tenant: str = Depends(tenant_id),
    ) -> dict[str, Any]:
        return service.agent_terminal_status(terminal_token, tenant)

    @application.get(
        "/v1/audit/verify",
        response_model=AuditVerificationResponse,
        dependencies=auditor,
    )
    def verify_audit() -> dict[str, Any]:
        return service.audit.verify()

    @application.get(
        "/v1/metrics",
        response_model=MetricsResponse,
        dependencies=auditor,
    )
    def metrics(tenant: str = Depends(tenant_id)) -> dict[str, Any]:
        return service.database.metrics()

    @application.get("/v1/model", dependencies=auditor)
    def model_status() -> dict[str, Any]:
        return service.model_status()

    @application.get("/v1/decisions/{decision_id}/replay", dependencies=auditor)
    def replay(decision_id: str, tenant: str = Depends(tenant_id)) -> dict[str, Any]:
        try:
            return service.replay_decision(decision_id, tenant)
        except NotFoundError as exc:
            raise translate_error(exc) from exc

    @application.post("/v1/events/{event_id}/lifecycle", dependencies=analyst)
    def lifecycle(event_id: str, request: LifecycleTransitionRequest, tenant: str = Depends(tenant_id)) -> dict[str, Any]:
        try:
            return service.transition_lifecycle(event_id, request, tenant)
        except (NotFoundError, ConflictError) as exc:
            raise translate_error(exc) from exc

    @application.get("/v1/cases", dependencies=analyst)
    def cases(tenant: str = Depends(tenant_id), limit: Annotated[int, Query(ge=1, le=500)] = 100) -> list[dict[str, Any]]:
        return service.database.list_cases(tenant, limit)

    @application.post("/v1/decisions/{decision_id}/appeals", dependencies=integration)
    def appeal(decision_id: str, request: AppealRequest, tenant: str = Depends(tenant_id)) -> dict[str, Any]:
        try:
            return service.create_appeal(decision_id, request, tenant)
        except NotFoundError as exc:
            raise translate_error(exc) from exc

    @application.post("/v1/consortium/reports", dependencies=analyst)
    def consortium_report(request: ConsortiumReportRequest) -> dict[str, Any]:
        return service.consortium_report(request)

    @application.post("/v1/fraud-sketch/reports", dependencies=analyst)
    def fraud_sketch_report(request: FraudSketchReportRequest) -> dict[str, Any]:
        try:
            return service.fraud_sketch_report(request)
        except (NotFoundError, ConflictError) as exc:
            raise translate_error(exc) from exc

    @application.post("/v1/fraud-sketch/reports/{report_id}/revoke", dependencies=analyst)
    def fraud_sketch_revoke(
        report_id: str,
        request: FraudSketchRevocationRequest,
    ) -> dict[str, Any]:
        try:
            return service.revoke_fraud_sketch_report(report_id, request)
        except (NotFoundError, ConflictError) as exc:
            raise translate_error(exc) from exc

    @application.get("/v1/fraud-sketch/status", dependencies=analyst)
    def fraud_sketch_status(
        indicator_type: FraudSketchIndicatorType,
        indicator_value: Annotated[str, Query(min_length=3, max_length=160)],
    ) -> dict[str, Any]:
        try:
            return service.fraud_sketch_status(indicator_type.value, indicator_value)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.post("/v1/policy/simulate", dependencies=auditor)
    def policy_simulation(request: PolicySimulationRequest, tenant: str = Depends(tenant_id)) -> dict[str, Any]:
        return service.policy_simulation(request, tenant)

    @application.get("/v1/governance/drift", dependencies=auditor)
    def drift(tenant: str = Depends(tenant_id)) -> dict[str, Any]:
        return service.drift_report(tenant)

    @application.get("/v1/governance/equity", dependencies=auditor)
    def equity(tenant: str = Depends(tenant_id)) -> dict[str, Any]:
        return service.equity_report(tenant)

    @application.post("/v1/privacy/requests", dependencies=integration)
    def privacy(request: PrivacyRequest, tenant: str = Depends(tenant_id)) -> dict[str, Any]:
        try:
            return service.privacy_request(request, tenant)
        except NotFoundError as exc:
            raise translate_error(exc) from exc

    @application.post("/v1/profiles/succession", dependencies=analyst)
    def profile_succession(request: ProfileSuccessionRequest, tenant: str = Depends(tenant_id)) -> dict[str, Any]:
        try:
            return service.profile_succession(request, tenant)
        except NotFoundError as exc:
            raise translate_error(exc) from exc

    @application.post("/v1/audit/anchor", dependencies=auditor)
    def anchor() -> dict[str, Any]:
        return service.audit_anchor()

    @application.get("/v1/observability", dependencies=auditor)
    def observability() -> dict[str, Any]:
        return service.telemetry.snapshot()

    @application.get("/v1/resilience/status", dependencies=integration)
    def resilience_status(tenant: str = Depends(tenant_id)) -> dict[str, Any]:
        return service.resilience_status(tenant)

    @application.post("/v1/resilience/heartbeat", dependencies=admin)
    def resilience_heartbeat(
        request: OutageHeartbeatRequest,
        tenant: str = Depends(tenant_id),
    ) -> dict[str, Any]:
        try:
            return service.resilience_heartbeat(request, tenant)
        except ConflictError as exc:
            raise translate_error(exc) from exc

    @application.post("/v1/resilience/simulate", dependencies=admin)
    def resilience_simulation(
        request: OutageSimulationRequest,
        tenant: str = Depends(tenant_id),
    ) -> dict[str, Any]:
        try:
            return service.simulate_resilience_mode(request, tenant)
        except ConflictError as exc:
            raise translate_error(exc) from exc

    @application.get("/v1/resilience/journal/verify", dependencies=auditor)
    def resilience_journal_verify(tenant: str = Depends(tenant_id)) -> dict[str, Any]:
        return service.database.verify_offline_journal(tenant)

    @application.post("/v1/resilience/reconcile", dependencies=auditor)
    def resilience_reconcile(
        request: ReconciliationRequest,
        tenant: str = Depends(tenant_id),
    ) -> dict[str, Any]:
        try:
            return service.reconcile_outage(request, tenant)
        except ConflictError as exc:
            raise translate_error(exc) from exc

    @application.get("/metrics", dependencies=auditor, response_class=Response)
    def prometheus() -> Response:
        return Response(service.telemetry.prometheus(), media_type="text/plain; version=0.0.4")

    return application
