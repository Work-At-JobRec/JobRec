import { Link, NavLink } from "react-router-dom";
import { useAuth0 } from "@auth0/auth0-react";

const navLinkClass =
  "text-[28px] font-bold justify-self-center text-white no-underline hover:text-[#E75A8F] transition-colors";

export default function Navbar() {
  const {
    isAuthenticated,
    isLoading,
    loginWithRedirect,
    logout,
  } = useAuth0();

  const handleLogout = () => {
    logout({
      logoutParams: {
        returnTo: window.location.origin,
      },
    });
  };

  return (
    <header
      className={`bg-black text-white grid ${
        isAuthenticated
          ? "grid-cols-[1.5fr_1fr_1fr_1fr_1fr]"
          : "grid-cols-[1.5fr_1fr_1fr_1fr]"
      } items-center py-2.5 px-[18px] min-h-[58px] w-full`}
    >
      <Link
        to="/"
        className="text-[30px] font-bold justify-self-start no-underline text-white hover:text-[#E75A8F] transition-colors"
      >
        JobRec
      </Link>

      <NavLink to="/jobs" className={navLinkClass}>
        Jobs
      </NavLink>

      <NavLink to="/search" className={navLinkClass}>
        Search
      </NavLink>

      {!isLoading && (
        isAuthenticated ? (
          <>
            <NavLink to="/profile" className={navLinkClass}>
              Profile
            </NavLink>

            <button
              type="button"
              onClick={handleLogout}
              className={`${navLinkClass} cursor-pointer`}
            >
              Log Out
            </button>
          </>
        ) : (
          <button
            type="button"
            onClick={() => loginWithRedirect()}
            className={`${navLinkClass} cursor-pointer`}
          >
            Log In
          </button>
        )
      )}
    </header>
  );
}
