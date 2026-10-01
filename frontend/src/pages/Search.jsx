import { useEffect, useRef, useState } from "react";
import Navbar from "../components/Navbar.jsx";
import LocationBar from "../components/LocationBar.jsx";
import JobCard from "../components/JobCard.jsx";
import { ChevronDownIcon, FunnelIcon, SearchIcon } from "../components/Icons.jsx";
import { fetchJobs } from "../api/jobs.js";
import { EMPTY_FILTERS, POSITION_TYPES, filterJobs } from "../utils/filterJobs.js";

const pill = "border-[1.5px] border-black rounded-full px-4 py-0.5 bg-transparent outline-none";

// Multi-select dropdown of position types; none selected means any type.
function PositionTypeSelect({ selected, onChange }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  // Close when clicking anywhere outside the dropdown.
  useEffect(() => {
    if (!open) return;
    const close = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const toggle = (type) =>
    onChange(selected.includes(type) ? selected.filter((t) => t !== type) : [...selected, type]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        id="position-type"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className={`${pill} flex items-center justify-between gap-4 w-[340px] text-left`}
      >
        <span className={`truncate ${selected.length ? "" : "text-[#8a8a8a]"}`}>
          {selected.length ? selected.join(", ") : "Any"}
        </span>
        <ChevronDownIcon className={`w-6 h-6 shrink-0 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <ul
          role="listbox"
          aria-multiselectable="true"
          className="absolute z-10 mt-2 w-full m-0 p-2 list-none bg-white border-[1.5px] border-black rounded-2xl shadow-md"
        >
          {POSITION_TYPES.map((type) => (
            <li key={type}>
              <label className="flex items-center gap-3 px-3 py-1.5 rounded-lg cursor-pointer hover:bg-[#f3f3f3]">
                <input
                  type="checkbox"
                  checked={selected.includes(type)}
                  onChange={() => toggle(type)}
                  className="w-5 h-5 accent-[#E75A8F]"
                />
                {type}
              </label>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Filters({ filters, update }) {
  return (
    <div className="mt-6 flex flex-col gap-8 text-[22px]">
      <LocationBar
        location={filters.location}
        radius={filters.radius}
        onLocationChange={(location) => update({ location })}
        onRadiusChange={(radius) => update({ radius })}
        placeholder="West Lafayette, IN"
      />

      <div className="flex flex-wrap items-center gap-x-3 gap-y-3">
        <label htmlFor="salary-min" className="font-bold mr-2">
          Salary:
        </label>
        <span>$</span>
        <input
          id="salary-min"
          inputMode="numeric"
          placeholder="60,000"
          value={filters.salaryMin}
          onChange={(e) => update({ salaryMin: e.target.value })}
          className={`${pill} w-[150px]`}
        />
        <span className="font-bold mx-2">to</span>
        <span>$</span>
        <input
          aria-label="Maximum salary"
          inputMode="numeric"
          placeholder="100,000"
          value={filters.salaryMax}
          onChange={(e) => update({ salaryMax: e.target.value })}
          className={`${pill} w-[150px]`}
        />
        <label htmlFor="salary-per" className="font-bold mx-2">
          per
        </label>
        <div className="relative">
          <select
            id="salary-per"
            value={filters.salaryPer}
            onChange={(e) => update({ salaryPer: e.target.value })}
            className={`${pill} w-[150px] cursor-pointer appearance-none`}
          >
            <option>Year</option>
            <option>Month</option>
            <option>Hour</option>
          </select>
          <ChevronDownIcon className="w-6 h-6 absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none" />
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-3">
        <label htmlFor="position-type" className="font-bold">
          Position Type:
        </label>
        <PositionTypeSelect selected={filters.positionTypes} onChange={(positionTypes) => update({ positionTypes })} />
      </div>

      <div className="flex flex-wrap items-center gap-x-8 gap-y-6">
        <div className="flex items-center gap-6">
          <label htmlFor="position-name" className="font-bold whitespace-nowrap">
            Position Name:
          </label>
          <input
            id="position-name"
            placeholder="Software Engineer"
            value={filters.positionName}
            onChange={(e) => update({ positionName: e.target.value })}
            className={`${pill} w-[300px] px-8`}
          />
        </div>
        <div className="flex items-center gap-6">
          <label htmlFor="company-name" className="font-bold whitespace-nowrap">
            Company Name:
          </label>
          <input
            id="company-name"
            placeholder="ACME Corporation"
            value={filters.companyName}
            onChange={(e) => update({ companyName: e.target.value })}
            className={`${pill} w-[300px] px-8`}
          />
        </div>
      </div>
    </div>
  );
}

export default function Search() {
  const [jobs, setJobs] = useState(null);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [filtersOpen, setFiltersOpen] = useState(true);

  useEffect(() => {
    fetchJobs()
      .then(setJobs)
      .catch((err) => {
        console.error(err);
        setError("Couldn't load jobs. Is the backend running?");
      });
  }, []);

  const update = (changes) => setFilters((current) => ({ ...current, ...changes }));
  const results = jobs && filterJobs(jobs, filters);

  return (
    <div className="min-h-screen bg-white">
      <Navbar />
      <main className="max-w-[1400px] mx-auto px-6 pb-16">
        <h1 className="text-center text-[56px] font-bold mt-24 mb-12">Here are the Best Jobs For You:</h1>

        <div className="max-w-[1100px] mx-auto">
          <form role="search" onSubmit={(e) => e.preventDefault()} className="flex items-center border-[1.5px] border-black rounded-full px-8 py-2 text-[26px]">
            <input
              type="search"
              aria-label="Search jobs by keyword"
              placeholder="Keywords"
              value={filters.keywords}
              onChange={(e) => update({ keywords: e.target.value })}
              className="flex-1 min-w-0 bg-transparent outline-none"
            />
            <SearchIcon className="w-8 h-8 text-[#8a8a8a] shrink-0" />
          </form>

          <div className="mt-12 flex items-center gap-6">
            <button
              type="button"
              aria-expanded={filtersOpen}
              onClick={() => setFiltersOpen((open) => !open)}
              className="inline-flex items-center gap-3 bg-black text-white text-xl font-bold rounded-2xl px-5 py-2.5"
            >
              <FunnelIcon className="w-6 h-6" />
              Filters
              <ChevronDownIcon className={`w-5 h-5 transition-transform ${filtersOpen ? "rotate-180" : ""}`} />
            </button>
            {filters !== EMPTY_FILTERS && (
              <button
                type="button"
                onClick={() => setFilters(EMPTY_FILTERS)}
                className="text-lg text-[#8a8a8a] hover:text-[#E75A8F] underline underline-offset-4"
              >
                Clear all
              </button>
            )}
          </div>

          {filtersOpen && <Filters filters={filters} update={update} />}
        </div>

        <hr className="border-0 border-t-[1.5px] border-black mt-8 mb-6" />

        <div className="flex flex-col gap-8 px-12" aria-live="polite">
          {error && <p className="text-2xl">{error}</p>}
          {!error && !results && <p className="text-2xl text-[#8a8a8a]">Loading jobs…</p>}
          {results?.length === 0 && <p className="text-2xl">No jobs match your search.</p>}
          {results?.map((job) => (
            <JobCard key={job.id} job={job} />
          ))}
        </div>
      </main>
    </div>
  );
}
