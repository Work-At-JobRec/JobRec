import { useAuth0 } from "@auth0/auth0-react";

export function useAuthenticatedUser() {
  const {
    user,
    isAuthenticated,
    isLoading,
    getAccessTokenSilently,
    error,
  } = useAuth0();

  return {
    user,
    isAuthenticated,
    isLoading,
    getAccessTokenSilently,
    error,
  };
}