import React from 'react';
import './Button.css';

const Button = ({
    children,
    variant = 'primary',
    size = 'md',
    onClick,
    disabled = false,
    type = 'button',
    className = '',
    icon: Icon,
    loading = false,
}) => {
    const classNames = [
        'btn',
        `btn-${variant}`,
        `btn-${size}`,
        disabled && 'btn-disabled',
        loading && 'btn-loading',
        className,
    ]
        .filter(Boolean)
        .join(' ');

    return (
        <button
            type={type}
            className={classNames}
            onClick={onClick}
            disabled={disabled || loading}
        >
            {loading ? (
                <>
                    <span className="btn-spinner animate-spin"></span>
                    <span>Loading...</span>
                </>
            ) : (
                <>
                    {Icon && <Icon size={size === 'sm' ? 16 : size === 'lg' ? 24 : 20} />}
                    <span>{children}</span>
                </>
            )}
        </button>
    );
};

export default Button;
