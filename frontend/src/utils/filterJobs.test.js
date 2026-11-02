// Unit tests for the Search tab filtering logic (frontend/src/utils/filterJobs.js).
// Run from frontend/:  node --test src/utils/filterJobs.test.js
import { test } from "node:test";
import assert from "node:assert/strict";

import { EMPTY_FILTERS, activeFilters, filterJobs, yearlySalary } from "./filterJobs.js";

const JOBS = [
  {
    title: "Backend Engineer",
    company: "Acme",
    location: "West Lafayette, IN",
    description: "Build APIs",
    salary: "USD 120,000 per year",
    jobType: "Full Time",
    requirements: [{ skill: "Python" }, { skill: "SQL" }],
  },
  {
    title: "Frontend Intern",
    company: "Globex",
    location: "Chicago, IL",
    description: "React components",
    salary: "$25/hr",
    jobType: "Internship",
    requirements: [{ skill: "React" }],
  },
  {
    title: "Data Analyst",
    company: "Initech",
    location: "Indianapolis, IN",
    description: "Dashboards",
    salary: "Competitive",
    jobType: "Part Time",
    requirements: [{ skill: "SQL" }],
  },
];

const withFilters = (changes) => ({ ...EMPTY_FILTERS, ...changes });
const titles = (jobs) => jobs.map((job) => job.title);

test("yearlySalary converts yearly, hourly and monthly pay to a yearly amount", () => {
  assert.equal(yearlySalary("USD 120,000 per year"), 120000);
  assert.equal(yearlySalary("100k/yr"), 100000);
  assert.equal(yearlySalary("$25/hr"), 52000);
  assert.equal(yearlySalary("5,000/mo"), 60000);
});

test("yearlySalary returns null when there is no number", () => {
  assert.equal(yearlySalary("Competitive"), null);
  assert.equal(yearlySalary(undefined), null);
});

test("empty filters return every job", () => {
  assert.deepEqual(titles(filterJobs(JOBS, EMPTY_FILTERS)), titles(JOBS));
});

test("keywords must all match, ignoring case, across title, company, description and skills", () => {
  assert.deepEqual(titles(filterJobs(JOBS, withFilters({ keywords: "PYTHON acme" }))), ["Backend Engineer"]);
  assert.deepEqual(titles(filterJobs(JOBS, withFilters({ keywords: "sql" }))), ["Backend Engineer", "Data Analyst"]);
  assert.deepEqual(filterJobs(JOBS, withFilters({ keywords: "python react" })), []);
});

test("location matches on the city, so 'West Lafayette, IN' finds the West Lafayette job", () => {
  assert.deepEqual(titles(filterJobs(JOBS, withFilters({ location: "West Lafayette, IN" }))), ["Backend Engineer"]);
  assert.deepEqual(titles(filterJobs(JOBS, withFilters({ location: "chicago" }))), ["Frontend Intern"]);
});

test("salary range compares yearly amounts and drops jobs whose pay can't be read", () => {
  // $25/hr = $52,000/yr, below the $60,000 minimum.
  assert.deepEqual(titles(filterJobs(JOBS, withFilters({ salaryMin: "60,000" }))), ["Backend Engineer"]);
  // An hourly range: $20-30/hr keeps the $25/hr internship only.
  assert.deepEqual(
    titles(filterJobs(JOBS, withFilters({ salaryMin: "20", salaryMax: "30", salaryPer: "Hour" }))),
    ["Frontend Intern"],
  );
});

test("position type, position name and company filters narrow the results", () => {
  assert.deepEqual(
    titles(filterJobs(JOBS, withFilters({ positionTypes: ["Internship", "Part Time"] }))),
    ["Frontend Intern", "Data Analyst"],
  );
  assert.deepEqual(titles(filterJobs(JOBS, withFilters({ positionName: "analyst" }))), ["Data Analyst"]);
  assert.deepEqual(titles(filterJobs(JOBS, withFilters({ companyName: "GLOBEX" }))), ["Frontend Intern"]);
});

test("filters that match nothing return an empty list (the 'no jobs found' case)", () => {
  assert.deepEqual(filterJobs(JOBS, withFilters({ companyName: "Nonexistent Co" })), []);
});

test("activeFilters lists each filter in use with the change that clears it", () => {
  assert.deepEqual(activeFilters(EMPTY_FILTERS), []);
  const active = activeFilters(withFilters({ keywords: " python ", salaryMin: "50000", positionTypes: ["Full Time"] }));
  assert.deepEqual(
    active.map((filter) => filter.label),
    ["Search: python", "Salary: $50000 – $any / Year", "Type: Full Time"],
  );
  assert.deepEqual(active[0].reset, { keywords: "" });
  assert.deepEqual(active[1].reset, { salaryMin: "", salaryMax: "" });
});
