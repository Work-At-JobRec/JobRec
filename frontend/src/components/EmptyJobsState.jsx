// Shown when a job list or search comes back with zero results.
// `children` holds the actionable suggestion for the page it's on.
export default function EmptyJobsState({ children }) {
  return (
    <div role="status" className="flex flex-col items-center text-center py-24">
      <p className="text-[34px] font-bold leading-snug">
        We looked everywhere…
        <br />
        there's 0 jobs to be found.
      </p>
      {children && <div className="mt-6 text-xl text-[#5a5a5a] max-w-[640px]">{children}</div>}
    </div>
  );
}
