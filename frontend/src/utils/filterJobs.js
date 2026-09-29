// Client-side filtering for the Search page. Empty filters match everything.

export const POSITION_TYPES = ["Full Time", "Part Time", "Internship", "Contract"];

// Multipliers to turn a salary in each period into a yearly amount.
const PER_YEAR = { Year: 1, Month: 12, Hour: 2080 };
const SALARY_UNITS = { yr: "Year", year: "Year", mo: "Month", month: "Month", hr: "Hour", hour: "Hour" };

export const EMPTY_FILTERS = {
  keywords: "",
  location: "",
  radius: 10,
  salaryMin: "",
  salaryMax: "",
  salaryPer: "Year",
  positionTypes: [],
  positionName: "",
  companyName: "",
};

// "100k/yr" -> 100000, "$25/hr" -> 52000 (yearly). Null if it can't be read.
export function yearlySalary(salary) {
  const match = /\$?\s*([\d,.]+)\s*(k)?\s*(?:\/|per\s+)?\s*([a-z]+)?/i.exec(salary ?? "");
  if (!match) return null;
  const amount = parseFloat(match[1].replace(/,/g, "")) * (match[2] ? 1000 : 1);
  const period = SALARY_UNITS[match[3]?.toLowerCase()] ?? "Year";
  return Number.isNaN(amount) ? null : amount * PER_YEAR[period];
}

// "60,000" -> 60000; blank or invalid -> null.
function parseAmount(text) {
  const value = parseFloat(String(text).replace(/[,$\s]/g, ""));
  return Number.isNaN(value) ? null : value;
}

function includes(haystack, needle) {
  return (haystack ?? "").toLowerCase().includes(needle.trim().toLowerCase());
}

export function filterJobs(jobs, filters) {
  const keywords = filters.keywords.trim().toLowerCase().split(/\s+/).filter(Boolean);
  // Match on the city only, so "West Lafayette" finds "West Lafayette, IN".
  const city = filters.location.split(",")[0];
  const perYear = PER_YEAR[filters.salaryPer];
  const min = parseAmount(filters.salaryMin);
  const max = parseAmount(filters.salaryMax);

  return jobs.filter((job) => {
    if (keywords.length) {
      const text = [job.title, job.company, job.description, ...job.requirements.map((r) => r.skill)]
        .join(" ")
        .toLowerCase();
      if (!keywords.every((word) => text.includes(word))) return false;
    }
    if (city.trim() && !includes(job.location, city)) return false;
    if (min != null || max != null) {
      const salary = yearlySalary(job.salary);
      if (salary == null) return false;
      if (min != null && salary < min * perYear) return false;
      if (max != null && salary > max * perYear) return false;
    }
    if (filters.positionTypes.length && !filters.positionTypes.includes(job.jobType)) return false;
    if (filters.positionName.trim() && !includes(job.title, filters.positionName)) return false;
    if (filters.companyName.trim() && !includes(job.company, filters.companyName)) return false;
    return true;
  });
}
