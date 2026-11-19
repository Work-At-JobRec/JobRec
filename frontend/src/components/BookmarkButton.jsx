import { useEffect, useState } from "react";
import { BookmarkIcon } from "./Icons.jsx";
import { fetchIsBookmarked, setBookmarked } from "../api/bookmarks.js";
import { useAuthenticatedUser } from "../hooks/useAuthenticatedUser.ts";

// Toggles a bookmark on one job. Black until hovered or bookmarked, then pink.
export default function BookmarkButton({ jobId, className = "" }) {
  // null = still loading the saved state
  const [bookmarked, setBookmarkedState] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const { getAccessTokenSilently, isAuthenticated } = useAuthenticatedUser();

  useEffect(() => {
    if (!isAuthenticated) return;
    let cancelled = false;
    setBookmarkedState(null);
    getAccessTokenSilently()
      .then((token) => fetchIsBookmarked(jobId, token))
      .then((saved) => !cancelled && setBookmarkedState(saved))
      .catch((err) => {
        console.error(err);
        if (!cancelled) setBookmarkedState(false);
      });
    return () => {
      cancelled = true;
    };
  }, [jobId, isAuthenticated, getAccessTokenSilently]);

  const toggle = async () => {
    const next = !bookmarked;
    setBookmarkedState(next); // show the change right away; undo it if saving fails
    setSaving(true);
    setError(null);
    try {
      const token = await getAccessTokenSilently();
      setBookmarkedState(await setBookmarked(jobId, next, token));
    } catch (err) {
      console.error(err);
      setBookmarkedState(!next);
      setError("Couldn't save your bookmark. Try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className={`flex flex-col items-end ${className}`}>
      <button
        type="button"
        onClick={toggle}
        disabled={bookmarked === null || saving}
        aria-pressed={bookmarked === true}
        className={`inline-flex items-center gap-3 text-white text-2xl font-bold rounded-full px-6 py-2 transition-colors disabled:cursor-wait ${
          bookmarked ? "bg-[#E066A3]" : "bg-black hover:bg-[#E066A3]"
        }`}
      >
        <BookmarkIcon className="w-7 h-7" />
        {bookmarked ? "Bookmarked" : "Bookmark"}
      </button>
      {error && (
        <p role="alert" className="m-0 mt-1 text-base text-[#C0504D]">
          {error}
        </p>
      )}
    </div>
  );
}
