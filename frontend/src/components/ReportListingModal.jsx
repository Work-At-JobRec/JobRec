import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { CheckIcon } from "./Icons.jsx";
import { REPORT_REASONS } from "../api/jobs.js";

const button =
  "bg-black hover:bg-[#E066A3] text-white text-2xl font-bold rounded-full px-12 py-2.5 transition-colors " +
  "disabled:bg-[#bdbdbd] disabled:cursor-not-allowed";

// Portaled to <body> so the fixed overlay isn't affected by the page's .page-zoom.
// onSubmit({ reason, details }) should return a promise; the success step only shows once it resolves.
export default function ReportListingModal({ onSubmit, onClose }) {
  const [reason, setReason] = useState(null);
  const [details, setDetails] = useState("");
  const [status, setStatus] = useState("idle"); // idle | submitting | error | submitted

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const canSubmit = reason && (reason !== "other" || details.trim()) && status !== "submitting";

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!canSubmit) return;
    setStatus("submitting");
    try {
      await onSubmit({ reason, details: reason === "other" ? details.trim() : null });
      setStatus("submitted");
    } catch (err) {
      console.error(err);
      setStatus("error");
    }
  };

  return createPortal(
    <div
      className="fade-in fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 font-['Inter',sans-serif]"
      onClick={onClose}
    >
      <div
        // key swaps the panel between steps so the zoom-in animation replays
        key={status === "submitted" ? "success" : "info"}
        role="dialog"
        aria-modal="true"
        aria-labelledby="report-listing-title"
        className="zoom-in w-full max-w-[560px] bg-white border-[1.5px] border-black rounded-3xl px-10 py-9"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="report-listing-title" className="m-0 text-center text-[40px] font-bold">
          Report Listing
        </h2>

        {status === "submitted" ? (
          <div className="flex flex-col items-center">
            <CheckIcon className="w-40 h-40 my-6" />
            <p className="m-0 mb-6 text-xl font-bold">Received!</p>
            <button type="button" className={button} onClick={onClose}>
              Close
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="mt-7 text-xl">
            <p className="m-0 mb-5 font-bold">Please state the reason for your report:</p>
            <div className="flex flex-col gap-3 pl-3">
              {REPORT_REASONS.map((r) => (
                <label key={r.code} className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="radio"
                    name="report-reason"
                    value={r.code}
                    checked={reason === r.code}
                    onChange={() => setReason(r.code)}
                    className="w-5 h-5 accent-[#E066A3] cursor-pointer"
                  />
                  {r.label}
                </label>
              ))}
              <textarea
                aria-label="Other reason"
                value={details}
                onChange={(e) => {
                  setDetails(e.target.value);
                  setReason("other");
                }}
                rows={3}
                maxLength={1000}
                className="ml-8 resize-none border-[1.5px] border-black rounded-2xl px-4 py-3 text-lg outline-none focus:border-[#E066A3]"
              />
            </div>
            {status === "error" && (
              <p className="m-0 mt-4 text-center text-lg text-[#C0504D]">
                Couldn't send your report. Please try again.
              </p>
            )}
            <div className="flex justify-center mt-8">
              <button type="submit" className={button} disabled={!canSubmit}>
                {status === "submitting" ? "Submitting…" : "Submit Report"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>,
    document.body
  );
}
