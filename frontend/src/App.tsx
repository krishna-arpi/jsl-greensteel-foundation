import { Route, Routes } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import TopBar from "./components/TopBar";
import ExecutiveDashboardPage from "./pages/ExecutiveDashboardPage";
import CalculatorPage from "./pages/CalculatorPage";
import AssumptionsPage from "./pages/AssumptionsPage";
import MaterialBalancePage from "./pages/MaterialBalancePage";
import AlloyChemistryPage from "./pages/AlloyChemistryPage";
import EmissionsPage from "./pages/EmissionsPage";
import ValidationPage from "./pages/ValidationPage";
import CarbonOptimizationPage from "./pages/CarbonOptimizationPage";
import SensitivityAnalysisPage from "./pages/SensitivityAnalysisPage";
import ScenarioComparisonPage from "./pages/ScenarioComparisonPage";
import UncertaintyAnalysisPage from "./pages/UncertaintyAnalysisPage";

export default function App() {
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-base-900">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main className="flex-1 overflow-y-auto p-4 lg:p-6">
          <Routes>
            <Route path="/" element={<ExecutiveDashboardPage />} />
            <Route path="/calculator" element={<CalculatorPage />} />
            <Route path="/assumptions" element={<AssumptionsPage />} />
            <Route path="/material-balance" element={<MaterialBalancePage />} />
            <Route path="/alloy-chemistry" element={<AlloyChemistryPage />} />
            <Route path="/emissions" element={<EmissionsPage />} />
            <Route path="/optimization" element={<CarbonOptimizationPage />} />
            <Route path="/sensitivity" element={<SensitivityAnalysisPage />} />
            <Route path="/scenarios" element={<ScenarioComparisonPage />} />
            <Route path="/validation" element={<ValidationPage />} />
            <Route path="/uncertainty" element={<UncertaintyAnalysisPage />} />
            <Route path="*" element={<ExecutiveDashboardPage />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
