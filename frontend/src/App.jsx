import { BrowserRouter, Routes, Route } from "react-router-dom";
import Home from "./pages/Home.jsx";
import Profile from "./pages/Profile.jsx";
import Jobs from "./pages/Jobs.jsx";
import JobDetail from "./pages/JobDetail.jsx";
import Search from "./pages/Search.jsx";
import Bookmarks from "./pages/Bookmarks.jsx";
import Applied from "./pages/Applied.jsx";
import Onboarding from "./pages/Onboarding.jsx"

export default function App() {
  return (
    <BrowserRouter>
      <div className="font-['Inter',sans-serif]">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/jobs" element={<Jobs />} />
          <Route path="/jobs/:id" element={<JobDetail />} />
          <Route path="/search" element={<Search />} />
          <Route path="/bookmarks" element={<Bookmarks />} />
          <Route path="/applied" element={<Applied />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/onboarding" element={<Onboarding />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
