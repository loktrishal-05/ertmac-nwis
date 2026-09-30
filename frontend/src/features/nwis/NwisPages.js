// Route entry for the NWIS workbench: one lazy chunk for all pages (MapLibre stays in its own chunk).
import './nwis.css'
export { DashboardPage, MapPage } from './pages/OverviewPages.jsx'
export { WellsPage, WellCockpitPage, ActiveWellRedirect, OffsetAnalysisPage, CorrelationPage } from './pages/WellPages.jsx'
export { EventsPage, RiskPage, LivePage, KnowledgeSearchPage } from './pages/IntelligencePages.jsx'
export { AdvisoriesPage, NwisAuditPage, HelpPage } from './pages/GovernancePages.jsx'
