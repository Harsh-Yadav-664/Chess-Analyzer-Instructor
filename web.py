"""
web.py
Premium web frontend server for AI Chess Instructor.

Serves a modern, responsive single-page application with:
- Interactive chessboard with drag-and-drop
- Real-time move analysis
- Suggestion arrows
- Profile tracking
- Mobile-responsive design
"""

from flask import Flask, render_template_string, send_from_directory
import os

app = Flask(__name__)

# =========================
# FRONTEND HTML/CSS/JS
# =========================

FRONTEND_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Chess Instructor - Premium Edition</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        :root {
            --bg-primary: #0f0f12;
            --bg-secondary: #18181b;
            --bg-tertiary: #27272a;
            --border-color: #3f3f46;
            --text-primary: #fafafa;
            --text-secondary: #a1a1aa;
            --accent-green: #10b981;
            --accent-blue: #3b82f6;
            --accent-red: #ef4444;
            --accent-yellow: #f59e0b;
            --accent-purple: #a855f7;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            overflow-x: hidden;
        }

        .container {
            max-width: 1600px;
            margin: 0 auto;
            padding: 20px;
        }

        /* Header */
        header {
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border-color);
            padding: 16px 0;
            margin-bottom: 24px;
        }

        .header-content {
            max-width: 1600px;
            margin: 0 auto;
            padding: 0 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 16px;
        }

        .logo {
            font-size: 24px;
            font-weight: bold;
            color: var(--accent-green);
        }

        .header-actions {
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
        }

        /* Main Layout */
        .main-layout {
            display: grid;
            grid-template-columns: 1fr 400px;
            gap: 24px;
            align-items: start;
        }

        /* Board Container */
        .board-section {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 20px;
        }

        .status-bar {
            width: 100%;
            max-width: 600px;
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
            text-align: center;
        }

        .status-title {
            font-size: 20px;
            font-weight: bold;
            color: var(--accent-green);
            margin-bottom: 8px;
        }

        .status-info {
            font-size: 14px;
            color: var(--text-secondary);
        }

        /* Chessboard */
        .board-wrapper {
            position: relative;
            width: fit-content;
        }

        .chessboard {
            display: grid;
            grid-template-columns: repeat(8, 70px);
            grid-template-rows: repeat(8, 70px);
            border: 3px solid var(--border-color);
            border-radius: 8px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
            position: relative;
            background: #fff;
        }

        .square {
            width: 70px;
            height: 70px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 48px;
            cursor: pointer;
            user-select: none;
            position: relative;
            transition: background-color 0.2s;
        }

        .square.light {
            background-color: #f0d9b5;
        }

        .square.dark {
            background-color: #b58863;
        }

        .square.selected {
            background-color: #829567 !important;
        }

        .square.legal-move::after {
            content: '';
            position: absolute;
            width: 24px;
            height: 24px;
            background: rgba(0, 0, 0, 0.2);
            border-radius: 50%;
        }

        .square.last-move {
            background-color: #cdd26a !important;
        }

        .square.check {
            background-color: rgba(239, 68, 68, 0.4) !important;
            box-shadow: inset 0 0 20px rgba(239, 68, 68, 0.6);
        }

        .piece {
            font-size: 48px;
            pointer-events: none;
        }

        .coordinates {
            position: absolute;
            font-size: 12px;
            color: var(--text-secondary);
            font-weight: bold;
        }

        .coord-file {
            bottom: -20px;
            left: 50%;
            transform: translateX(-50%);
        }

        .coord-rank {
            left: -20px;
            top: 50%;
            transform: translateY(-50%);
        }

        /* Side Panel */
        .side-panel {
            display: flex;
            flex-direction: column;
            gap: 20px;
        }

        .panel-card {
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
        }

        .panel-card h3 {
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 16px;
            color: var(--text-primary);
            display: flex;
            align-items: center;
            gap: 8px;
        }

        /* Settings */
        .setting-group {
            margin-bottom: 16px;
        }

        .setting-label {
            font-size: 12px;
            color: var(--text-secondary);
            font-weight: 600;
            margin-bottom: 8px;
            display: block;
        }

        select {
            width: 100%;
            padding: 10px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            color: var(--text-primary);
            font-size: 14px;
            cursor: pointer;
        }

        select:focus {
            outline: 2px solid var(--accent-blue);
        }

        /* Suggestions */
        .suggestion-item {
            background: var(--bg-tertiary);
            border-radius: 6px;
            padding: 12px;
            margin-bottom: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .suggestion-move {
            font-weight: bold;
            font-size: 14px;
        }

        .suggestion-eval {
            color: var(--text-secondary);
            font-size: 12px;
        }

        .suggestion-rank {
            font-size: 20px;
            margin-right: 12px;
        }

        /* Analysis */
        .analysis-content {
            max-height: 400px;
            overflow-y: auto;
            padding-right: 8px;
        }

        .move-analysis {
            background: var(--bg-tertiary);
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 12px;
        }

        .move-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }

        .move-title {
            font-size: 18px;
            font-weight: bold;
        }

        .move-grade {
            padding: 4px 12px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
        }

        .grade-BEST { background: var(--accent-green); color: white; }
        .grade-EXCELLENT { background: var(--accent-green); color: white; }
        .grade-GOOD { background: var(--accent-blue); color: white; }
        .grade-INACCURACY { background: var(--accent-yellow); color: white; }
        .grade-MISTAKE { background: var(--accent-red); color: white; }
        .grade-BLUNDER { background: var(--accent-purple); color: white; }

        .eval-change {
            font-size: 14px;
            color: var(--text-secondary);
            margin-bottom: 8px;
        }

        .explanation {
            font-size: 14px;
            line-height: 1.6;
            color: var(--text-primary);
            background: var(--bg-primary);
            padding: 12px;
            border-radius: 6px;
            border-left: 3px solid var(--accent-blue);
        }

        .alternatives {
            margin-top: 12px;
            padding-top: 12px;
            border-top: 1px solid var(--border-color);
        }

        .alternatives h4 {
            font-size: 14px;
            margin-bottom: 8px;
            color: var(--text-secondary);
        }

        .alt-move {
            font-size: 13px;
            padding: 6px;
            margin: 4px 0;
            background: var(--bg-primary);
            border-radius: 4px;
        }

        /* Stats Bar */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 12px;
        }

        .stat-item {
            background: var(--bg-tertiary);
            padding: 12px;
            border-radius: 6px;
            text-align: center;
        }

        .stat-value {
            font-size: 24px;
            font-weight: bold;
            margin-bottom: 4px;
        }

        .stat-label {
            font-size: 12px;
            color: var(--text-secondary);
        }

        /* Buttons */
        button {
            padding: 10px 20px;
            border: none;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }

        .btn-primary {
            background: var(--accent-green);
            color: white;
        }

        .btn-primary:hover {
            background: #059669;
        }

        .btn-secondary {
            background: var(--bg-tertiary);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
        }

        .btn-secondary:hover {
            background: var(--border-color);
        }

        .btn-danger {
            background: var(--accent-red);
            color: white;
        }

        .btn-danger:hover {
            background: #dc2626;
        }

        .button-group {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }

        /* Scrollbar */
        ::-webkit-scrollbar {
            width: 8px;
        }

        ::-webkit-scrollbar-track {
            background: var(--bg-tertiary);
            border-radius: 4px;
        }

        ::-webkit-scrollbar-thumb {
            background: var(--border-color);
            border-radius: 4px;
        }

        ::-webkit-scrollbar-thumb:hover {
            background: #52525b;
        }

        /* Loading Indicator */
        .loading {
            text-align: center;
            padding: 20px;
            color: var(--text-secondary);
        }

        .spinner {
            border: 3px solid var(--bg-tertiary);
            border-top: 3px solid var(--accent-green);
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 0 auto 12px;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        /* Modal */
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.8);
            z-index: 1000;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }

        .modal.active {
            display: flex;
        }

        .modal-content {
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 32px;
            max-width: 500px;
            width: 100%;
            max-height: 80vh;
            overflow-y: auto;
        }

        .modal-header {
            font-size: 24px;
            font-weight: bold;
            margin-bottom: 20px;
            text-align: center;
        }

        .modal-body {
            margin-bottom: 24px;
        }

        .modal-footer {
            display: flex;
            gap: 12px;
            justify-content: flex-end;
        }

        /* Responsive Design */
        @media (max-width: 1200px) {
            .main-layout {
                grid-template-columns: 1fr;
            }

            .side-panel {
                order: -1;
            }
        }

        @media (max-width: 768px) {
            .chessboard {
                grid-template-columns: repeat(8, 50px);
                grid-template-rows: repeat(8, 50px);
            }

            .square {
                width: 50px;
                height: 50px;
            }

            .piece {
                font-size: 36px;
            }

            .header-content {
                flex-direction: column;
                align-items: stretch;
            }

            .stats-grid {
                grid-template-columns: 1fr;
            }
        }

        @media (max-width: 480px) {
            .chessboard {
                grid-template-columns: repeat(8, 40px);
                grid-template-rows: repeat(8, 40px);
            }

            .square {
                width: 40px;
                height: 40px;
            }

            .piece {
                font-size: 28px;
            }

            .container {
                padding: 12px;
            }
        }
    </style>
</head>
<body>
    <header>
        <div class="header-content">
            <div class="logo">♟️ AI Chess Instructor</div>
            <div class="header-actions">
                <button class="btn-secondary" onclick="showProfile()">📊 Profile</button>
                <button class="btn-primary" onclick="newGame()">🔄 New Game</button>
            </div>
        </div>
    </header>

    <div class="container">
        <div class="main-layout">
            <!-- Board Section -->
            <div class="board-section">
                <div class="status-bar">
                    <div class="status-title" id="status-title">Your Turn</div>
                    <div class="status-info" id="status-info">Make your move</div>
                </div>

                <div class="board-wrapper">
                    <div class="chessboard" id="chessboard"></div>
                </div>

                <div class="button-group">
                    <button class="btn-secondary" onclick="undoMove()">⟲ Undo</button>
                    <button class="btn-secondary" onclick="showAnalysis()">🔍 Analysis</button>
                </div>
            </div>

            <!-- Side Panel -->
            <div class="side-panel">
                <!-- Settings -->
                <div class="panel-card">
                    <h3>⚙️ Settings</h3>
                    <div class="setting-group">
                        <label class="setting-label">Coach Mode</label>
                        <select id="instructor-mode" onchange="updateSettings()">
                            <option value="adaptive">Adaptive</option>
                            <option value="learning">Learning</option>
                            <option value="easy">Easy</option>
                            <option value="medium">Medium</option>
                            <option value="hard">Hard</option>
                        </select>
                    </div>
                    <div class="setting-group">
                        <label class="setting-label">Difficulty</label>
                        <select id="difficulty-mode" onchange="updateSettings()">
                            <option value="beginner">Beginner</option>
                            <option value="intermediate" selected>Intermediate</option>
                            <option value="advanced">Advanced</option>
                            <option value="engine">Engine</option>
                            <option value="adaptive">Adaptive</option>
                        </select>
                    </div>
                </div>

                <!-- Suggestions -->
                <div class="panel-card">
                    <h3>💡 Suggested Moves</h3>
                    <div id="suggestions-container">
                        <div class="loading">
                            <div class="spinner"></div>
                            Loading suggestions...
                        </div>
                    </div>
                </div>

                <!-- Move Analysis -->
                <div class="panel-card">
                    <h3>📊 Move Analysis</h3>
                    <div class="analysis-content" id="analysis-container">
                        <p style="color: var(--text-secondary); text-align: center; padding: 20px;">
                            Make a move to see analysis
                        </p>
                    </div>
                </div>

                <!-- Stats -->
                <div class="panel-card">
                    <h3>📈 Current Game</h3>
                    <div class="stats-grid" id="stats-container">
                        <div class="stat-item">
                            <div class="stat-value" id="stat-moves">0</div>
                            <div class="stat-label">Moves</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-value" id="stat-blunders" style="color: var(--accent-purple)">0</div>
                            <div class="stat-label">Blunders</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-value" id="stat-mistakes" style="color: var(--accent-red)">0</div>
                            <div class="stat-label">Mistakes</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-value" id="stat-good" style="color: var(--accent-green)">0</div>
                            <div class="stat-label">Good Moves</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Profile Modal -->
    <div class="modal" id="profile-modal">
        <div class="modal-content">
            <div class="modal-header">📊 Player Profile</div>
            <div class="modal-body" id="profile-content">
                <div class="loading">
                    <div class="spinner"></div>
                    Loading profile...
                </div>
            </div>
            <div class="modal-footer">
                <button class="btn-danger" onclick="resetProfile()">Reset Profile</button>
                <button class="btn-primary" onclick="closeModal()">Close</button>
            </div>
        </div>
    </div>

    <!-- Game Over Modal -->
    <div class="modal" id="gameover-modal">
        <div class="modal-content">
            <div class="modal-header" id="gameover-title">🏁 Game Over</div>
            <div class="modal-body" id="gameover-content"></div>
            <div class="modal-footer">
                <button class="btn-primary" onclick="closeGameOver()">Continue</button>
            </div>
        </div>
    </div>

    <script>
        // =========================
        // GLOBAL STATE
        // =========================
        const API_URL = 'http://localhost:5000/api';
        
        let boardState = null;
        let selectedSquare = null;
        let legalMoves = [];
        let moveHistory = [];
        let gameActive = true;

        const PIECE_UNICODE = {
            'K': '♔', 'Q': '♕', 'R': '♖', 'B': '♗', 'N': '♘', 'P': '♙',
            'k': '♚', 'q': '♛', 'r': '♜', 'b': '♝', 'n': '♞', 'p': '♟'
        };

        // =========================
        // INITIALIZATION
        // =========================
        async function initGame() {
            try {
                const response = await fetch(`${API_URL}/init`, {
                    method: 'POST',
                    credentials: 'include'
                });
                const data = await response.json();
                
                if (data.success) {
                    boardState = data.board;
                    renderBoard();
                    loadSuggestions();
                    updateStats();
                } else {
                    alert('Failed to initialize game: ' + data.error);
                }
            } catch (error) {
                console.error('Init error:', error);
                alert('Failed to connect to server. Please ensure the backend is running.');
            }
        }

        // =========================
        // BOARD RENDERING
        // =========================
        function renderBoard() {
            const board = document.getElementById('chessboard');
            board.innerHTML = '';

            const pieces = parseFEN(boardState.fen);

            for (let rank = 7; rank >= 0; rank--) {
                for (let file = 0; file < 8; file++) {
                    const square = document.createElement('div');
                    const squareIndex = rank * 8 + file;
                    const squareName = indexToSquare(squareIndex);
                    
                    square.className = 'square';
                    square.className += (rank + file) % 2 === 0 ? ' dark' : ' light';
                    square.dataset.square = squareName;
                    square.onclick = () => handleSquareClick(squareName);

                    // Highlight check
                    if (boardState.is_check && pieces[squareIndex] && 
                        ((boardState.turn === 'white' && pieces[squareIndex] === 'K') ||
                         (boardState.turn === 'black' && pieces[squareIndex] === 'k'))) {
                        square.classList.add('check');
                    }

                    // Add piece
                    if (pieces[squareIndex]) {
                        const piece = document.createElement('span');
                        piece.className = 'piece';
                        piece.textContent = PIECE_UNICODE[pieces[squareIndex]];
                        square.appendChild(piece);
                    }

                    board.appendChild(square);
                }
            }

            updateStatus();
        }

        function parseFEN(fen) {
            const pieces = new Array(64).fill(null);
            const rows = fen.split(' ')[0].split('/');
            
            let index = 0;
            for (let rank = 7; rank >= 0; rank--) {
                const row = rows[7 - rank];
                let file = 0;
                
                for (let char of row) {
                    if (isNaN(char)) {
                        pieces[rank * 8 + file] = char;
                        file++;
                    } else {
                        file += parseInt(char);
                    }
                }
            }
            
            return pieces;
        }

        function indexToSquare(index) {
            const file = String.fromCharCode(97 + (index % 8));
            const rank = Math.floor(index / 8) + 1;
            return file + rank;
        }

        function squareToIndex(square) {
            const file = square.charCodeAt(0) - 97;
            const rank = parseInt(square[1]) - 1;
            return rank * 8 + file;
        }

        // =========================
        // MOVE HANDLING
        // =========================
        async function handleSquareClick(square) {
            if (!gameActive || boardState.turn !== 'white') return;

            // If square is a legal move destination
            if (selectedSquare && legalMoves.includes(square)) {
                await makeMove(selectedSquare + square);
                clearSelection();
                return;
            }

            // Select new square
            clearSelection();
            
            const moves = boardState.legal_moves.filter(m => m.startsWith(square.substring(0, 2)));
            if (moves.length > 0) {
                selectedSquare = square;
                legalMoves = moves.map(m => m.substring(2, 4));
                highlightSelection();
            }
        }

        function highlightSelection() {
            const squares = document.querySelectorAll('.square');
            squares.forEach(sq => {
                sq.classList.remove('selected', 'legal-move');
                
                if (sq.dataset.square === selectedSquare) {
                    sq.classList.add('selected');
                }
                
                if (legalMoves.includes(sq.dataset.square)) {
                    sq.classList.add('legal-move');
                }
            });
        }

        function clearSelection() {
            selectedSquare = null;
            legalMoves = [];
            document.querySelectorAll('.square').forEach(sq => {
                sq.classList.remove('selected', 'legal-move');
            });
        }

        async function makeMove(moveUCI) {
            try {
                updateStatus('Analyzing your move...', 'var(--accent-blue)');
                
                const response = await fetch(`${API_URL}/move`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify({ move: moveUCI })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    boardState = data.board;
                    moveHistory.push(data.assessment);
                    
                    renderBoard();
                    displayMoveAnalysis(data.assessment, data.alternatives, data.warning);
                    updateStats();
                    
                    if (data.game_over) {
                        handleGameOver(data.game_over);
                    } else {
                        loadSuggestions();
                    }
                } else {
                    alert('Invalid move: ' + data.error);
                    renderBoard();
                }
            } catch (error) {
                console.error('Move error:', error);
                alert('Failed to make move');
                renderBoard();
            }
        }

        // =========================
        // UI UPDATES
        // =========================
        function updateStatus(message = null, color = null) {
            const title = document.getElementById('status-title');
            const info = document.getElementById('status-info');
            
            if (message) {
                title.textContent = message;
                if (color) title.style.color = color;
                return;
            }

            if (!boardState) return;

            if (boardState.is_checkmate) {
                title.textContent = '🏁 Checkmate!';
                title.style.color = 'var(--accent-red)';
                info.textContent = boardState.turn === 'white' ? 'Black wins!' : 'White wins!';
            } else if (boardState.is_stalemate) {
                title.textContent = '🤝 Stalemate';
                title.style.color = 'var(--accent-yellow)';
                info.textContent = 'Draw';
            } else if (boardState.is_check) {
                title.textContent = '⚠️ Check!';
                title.style.color = 'var(--accent-red)';
                info.textContent = 'You must move your king';
            } else if (boardState.turn === 'white') {
                title.textContent = '♟️ Your Turn';
                title.style.color = 'var(--accent-green)';
                info.textContent = 'Make your move';
            } else {
                title.textContent = '🤖 Engine Thinking...';
                title.style.color = 'var(--accent-blue)';
                info.textContent = 'Please wait';
            }
        }

        async function loadSuggestions() {
            const container = document.getElementById('suggestions-container');
            container.innerHTML = '<div class="loading"><div class="spinner"></div>Loading...</div>';
            
            try {
                const response = await fetch(`${API_URL}/suggestions`, {
                    credentials: 'include'
                });
                const data = await response.json();
                
                if (data.success && data.suggestions.length > 0) {
                    container.innerHTML = data.suggestions.map((sug, i) => `
                        <div class="suggestion-item">
                            <div style="display: flex; align-items: center;">
                                <span class="suggestion-rank">${['🥇', '🥈', '🥉'][i]}</span>
                                <div>
                                    <div class="suggestion-move">${sug.move}</div>
                                    <div class="suggestion-eval">${formatEval(sug)}</div>
                                </div>
                            </div>
                        </div>
                    `).join('');
                } else {
                    container.innerHTML = '<p style="color: var(--text-secondary); text-align: center;">No suggestions available</p>';
                }
            } catch (error) {
                console.error('Suggestions error:', error);
                container.innerHTML = '<p style="color: var(--accent-red); text-align: center;">Failed to load</p>';
            }
        }

        function displayMoveAnalysis(assessment, alternatives, warning) {
            const container = document.getElementById('analysis-container');
            
            let html = '';
            
            if (warning) {
                html += `<div style="background: rgba(245, 158, 11, 0.2); padding: 12px; border-radius: 6px; margin-bottom: 12px; border-left: 3px solid var(--accent-yellow);">
                    ⚠️ <b>Warning:</b> ${warning}
                </div>`;
            }
            
            html += `
                <div class="move-analysis">
                    <div class="move-header">
                        <div class="move-title">${assessment.move}</div>
                        <div class="move-grade grade-${assessment.grade}">${assessment.grade}</div>
                    </div>
                    <div class="eval-change">
                        Eval: ${assessment.eval_initial.toFixed(2)} → ${assessment.eval_final.toFixed(2)}
                    </div>
                    <div class="explanation">${assessment.explanation}</div>
            `;
            
            if (alternatives && alternatives.length > 0) {
                html += `
                    <div class="alternatives">
                        <h4>Alternative Moves:</h4>
                        ${alternatives.map((alt, i) => `
                            <div class="alt-move">
                                ${i + 1}. <b>${alt.move}</b> (${formatEval(alt)})
                            </div>
                        `).join('')}
                    </div>
                `;
            }
            
            html += '</div>';
            container.innerHTML = html;
        }

        function formatEval(item) {
            if (item.is_mate) {
                return `M${Math.abs(item.mate_in)}`;
            }
            return item.eval ? `${item.eval > 0 ? '+' : ''}${item.eval.toFixed(2)}` : '0.00';
        }

        async function updateStats() {
            try {
                const response = await fetch(`${API_URL}/profile`, {
                    credentials: 'include'
                });
                const data = await response.json();
                
                if (data.success && data.profile.current_game) {
                    const stats = data.profile.current_game;
                    document.getElementById('stat-moves').textContent = stats.move_count;
                    document.getElementById('stat-blunders').textContent = stats.blunders;
                    document.getElementById('stat-mistakes').textContent = stats.mistakes;
                    document.getElementById('stat-good').textContent = stats.good_moves;
                }
            } catch (error) {
                console.error('Stats error:', error);
            }
        }

        // =========================
        // ACTIONS
        // =========================
        async function undoMove() {
            try {
                const response = await fetch(`${API_URL}/undo`, {
                    method: 'POST',
                    credentials: 'include'
                });
                const data = await response.json();
                
                if (data.success) {
                    boardState = data.board;
                    renderBoard();
                    loadSuggestions();
                }
            } catch (error) {
                console.error('Undo error:', error);
            }
        }

        async function newGame() {
            if (confirm('Start a new game? Current game will be saved to your profile.')) {
                await initGame();
            }
        }

        async function updateSettings() {
            const instructorMode = document.getElementById('instructor-mode').value;
            const difficultyMode = document.getElementById('difficulty-mode').value;
            
            try {
                await fetch(`${API_URL}/settings`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify({
                        instructor_mode: instructorMode,
                        difficulty_mode: difficultyMode
                    })
                });
            } catch (error) {
                console.error('Settings error:', error);
            }
        }

        async function showProfile() {
            const modal = document.getElementById('profile-modal');
            const content = document.getElementById('profile-content');
            
            modal.classList.add('active');
            content.innerHTML = '<div class="loading"><div class="spinner"></div>Loading...</div>';
            
            try {
                const response = await fetch(`${API_URL}/profile`, {
                    credentials: 'include'
                });
                const data = await response.json();
                
                if (data.success) {
                    content.innerHTML = `
                        <div style="margin-bottom: 20px;">
                            ${data.profile.summary}
                        </div>
                        ${data.profile.training_suggestion ? `
                            <div style="background: var(--bg-tertiary); padding: 16px; border-radius: 8px; border-left: 3px solid var(--accent-blue);">
                                <h4 style="margin-bottom: 8px;">💡 Training Suggestion</h4>
                                <p>${data.profile.training_suggestion}</p>
                            </div>
                        ` : ''}
                    `;
                }
            } catch (error) {
                console.error('Profile error:', error);
                content.innerHTML = '<p style="color: var(--accent-red);">Failed to load profile</p>';
            }
        }

        function closeModal() {
            document.getElementById('profile-modal').classList.remove('active');
        }

        async function resetProfile() {
            if (confirm('Are you sure? This will delete all your statistics and cannot be undone.')) {
                try {
                    await fetch(`${API_URL}/profile/reset`, {
                        method: 'POST',
                        credentials: 'include'
                    });
                    alert('Profile reset successfully');
                    closeModal();
                } catch (error) {
                    console.error('Reset error:', error);
                    alert('Failed to reset profile');
                }
            }
        }

        function handleGameOver(gameOverData) {
            gameActive = false;
            
            const modal = document.getElementById('gameover-modal');
            const title = document.getElementById('gameover-title');
            const content = document.getElementById('gameover-content');
            
            const result = gameOverData.result;
            const icon = result.includes('1-0') ? '🏆' : result.includes('0-1') ? '😔' : '🤝';
            
            title.textContent = `${icon} Game Over - ${result}`;
            
            const feedback = gameOverData.feedback;
            content.innerHTML = `
                <div style="text-align: center; margin-bottom: 20px;">
                    <div style="font-size: 18px; font-weight: bold; margin-bottom: 16px;">
                        ${feedback.summary}
                    </div>
                    <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-top: 16px;">
                        <div class="stat-item">
                            <div class="stat-value">${feedback.total_moves}</div>
                            <div class="stat-label">Total Moves</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-value" style="color: var(--accent-purple)">${feedback.blunders}</div>
                            <div class="stat-label">Blunders</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-value" style="color: var(--accent-red)">${feedback.mistakes}</div>
                            <div class="stat-label">Mistakes</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-value" style="color: var(--accent-green)">${feedback.good_moves}</div>
                            <div class="stat-label">Good Moves</div>
                        </div>
                    </div>
                </div>
            `;
            
            modal.classList.add('active');
        }

        function closeGameOver() {
            document.getElementById('gameover-modal').classList.remove('active');
        }

        function showAnalysis() {
            // Scroll to analysis panel on mobile
            document.getElementById('analysis-container').scrollIntoView({ behavior: 'smooth' });
        }

        // =========================
        // INITIALIZE ON LOAD
        // =========================
        window.addEventListener('load', initGame);
    </script>
</body>
</html>
"""

# =========================
# ROUTES
# =========================

@app.route('/')
def index():
    """Serve the main frontend page."""
    return render_template_string(FRONTEND_HTML)


@app.route('/health')
def health():
    """Health check endpoint."""
    return {'status': 'running', 'frontend': 'active'}


# =========================
# MAIN
# =========================

if __name__ == '__main__':
    print("=" * 50)
    print("AI Chess Instructor - Web Frontend")
    print("=" * 50)
    print("✓ Frontend server ready")
    print("✓ Open your browser to: http://localhost:5001")
    print("=" * 50)
    app.run(debug=True, host='0.0.0.0', port=5001)