import { useEffect } from 'react';
import { useAuth } from '../context/AuthContext';

/**
 * Mantiene la sesión activa mientras hay un proceso de carga en curso.
 */
export const useSessionLoadGuard = (active) => {
    const { registerLoadProcess } = useAuth();

    useEffect(() => {
        if (!active) return undefined;
        return registerLoadProcess();
    }, [active, registerLoadProcess]);
};

export default useSessionLoadGuard;
