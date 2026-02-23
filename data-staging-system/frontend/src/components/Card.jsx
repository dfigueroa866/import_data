import React from 'react';
import './Card.css';

const Card = ({
    children,
    title,
    subtitle,
    className = '',
    hoverable = false,
    onClick,
}) => {
    const classNames = [
        'card',
        'glass-card',
        hoverable && 'card-hoverable',
        onClick && 'card-clickable',
        className,
    ]
        .filter(Boolean)
        .join(' ');

    return (
        <div className={classNames} onClick={onClick}>
            {(title || subtitle) && (
                <div className="card-header">
                    {title && <h3 className="card-title">{title}</h3>}
                    {subtitle && <p className="card-subtitle">{subtitle}</p>}
                </div>
            )}
            <div className="card-content">{children}</div>
        </div>
    );
};

export default Card;
