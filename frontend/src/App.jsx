import { BrowserRouter, Routes, Route } from "react-router-dom";
import Home from "./pages/Home.jsx";
import Profile from "./pages/Profile.jsx";
import Jobs from "./pages/Jobs.jsx";
import JobDetail from "./pages/JobDetail.jsx";

export default function App() {
  return (
    <BrowserRouter>
      <div className="font-['Inter',sans-serif]">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/jobs" element={<Jobs />} />
          <Route path="/jobs/:id" element={<JobDetail />} />
          <Route path="/profile" element={<Profile />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
