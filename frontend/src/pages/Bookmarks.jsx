import SavedJobsPage from "../components/SavedJobsPage.jsx";

export default function Bookmarks() {
  return (
    <SavedJobsPage
      list="bookmarks"
      title="Jobs you’ve Bookmarked:"
      emptyMessage="None so far… find your favorites!"
    />
  );
}
