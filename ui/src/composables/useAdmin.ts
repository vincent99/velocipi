export function useAdmin() {
  const isAdmin = document.cookie
    .split(';')
    .some((c) => c.trim() === 'admin=true');
  return { isAdmin };
}
