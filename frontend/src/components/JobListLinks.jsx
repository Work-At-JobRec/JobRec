import { Link } from "react-router-dom";

const buttonClass =
  "inline-flex items-center justify-center min-w-[220px] bg-black text-white text-xl font-bold rounded-full px-8 py-1.5 no-underline transition-colors hover:bg-[#E066A3]";

// The "Applied Jobs" and "Bookmarks" buttons under the Jobs and Search headings.
// Bookmarks opens the user's saved jobs in a new tab; Applied Jobs isn't built yet.
export default function JobListLinks() {
  return (
    <div className="flex flex-wrap justify-center gap-4">
      <button type="button" aria-disabled="true" title="Coming soon" className={buttonClass}>
        Applied Jobs
      </button>
      <Link to="/bookmarks" target="_blank" rel="noopener noreferrer" className={buttonClass}>
        Bookmarks
      </Link>
    </div>
  );
}
