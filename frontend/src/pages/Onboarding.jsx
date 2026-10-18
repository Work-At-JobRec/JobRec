import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth0 } from "@auth0/auth0-react";

const fields = [
  { name: "name", label: "Name", type: "text" },
  { name: "email", label: "Email", type: "email" },
  { name: "phone", label: "Phone Number", type: "tel" },
  { name: "address", label: "Address", type: "text" },
];

export default function Onboarding() {
  const {
    isAuthenticated,
    isLoading,
    getAccessTokenSilently,
    loginWithRedirect,
  } = useAuth0();

  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    if (submitting) return;

    setError("");

    if (!isAuthenticated) {
      setError("You must be logged in to save your profile.");
      return;
    }

    // Read form data before awaiting anything.
    const formData = new FormData(e.currentTarget);
    setSubmitting(true);

    try {
      // Obtain a valid token for this request.
      const token = await getAccessTokenSilently();

      if (!token) {
        throw new Error("Could not obtain an authentication token.");
      }

      const res = await fetch("/api/onboarding", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: formData,
      });

      if (!res.ok) {
        if (res.status === 401) {
          throw new Error(
            "Your session could not be verified. Please log in again."
          );
        }

        throw new Error(
          `Could not save your profile (HTTP ${res.status}).`
        );
      }

      // Success: return to the profile without reloading.
      navigate("/profile", { replace: true });

    } catch (err) {
      console.error("Onboarding submission failed:", err);
      setError(
        err.message || "Something went wrong. Please try again."
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex flex-col items-center min-h-screen pt-20 text-center">
      <h1 className="text-[96px] font-bold text-black mt-20 mb-5">
        Welcome, new user
      </h1>

      <p className="text-[22px] text-black text-center">
        Complete your profile:
      </p>

      {isLoading && <p>Checking your login...</p>}

      {!isLoading && !isAuthenticated && (
        <div>
          <p>Your login session is unavailable.</p>
          <button type="button" onClick={() => loginWithRedirect()}>
            Log in again
          </button>
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <div className="grid gap-6 mb-6 md:grid-cols-2">
          {fields.map((field) => (
            <div key={field.name}>
              <label
                htmlFor={field.name}
                className="block mb-2.5 text-sm font-medium"
              >
                {field.label}
              </label>

              <input
                type={field.type}
                id={field.name}
                name={field.name}
                className="bg-neutral-secondary-medium border border-default-medium text-sm rounded-base block w-full px-3 py-2.5 shadow-xs text-body"
                required
              />
            </div>
          ))}
        </div>

        {error && (
          <p role="alert" className="text-red-600 mb-4">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={submitting || isLoading || !isAuthenticated}
          className="text-black bg-brand box-border border disabled:opacity-50"
        >
          {submitting ? "Saving..." : "Submit"}
        </button>
      </form>
    </div>
  );
}
