import SavedJobsPage from "../components/SavedJobsPage.jsx";

export default function Applied() {
  return (
    <SavedJobsPage
      list="applied"
      title="Jobs you’ve Applied to:"
      emptyMessage="None so far… start the hunt!"
    />
  );
}
