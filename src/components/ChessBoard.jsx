import { useState } from "react";  //to store changing data
import { Chess } from "chess.js"; //rules engine
import { Chessboard } from "react-chessboard"; //UI of the chessboard

export default function ChessBoard(){
    const [game, setGame] = useState(new Chess()); //game= current chess game; new Chess()= starts new game with default initial position ; usestate= when game changes react re-renders the board
   
    function onPieceDrop(from,to){
        const gameCopy = new Chess(game.fen()); 
        const move = gameCopy.move({from, to, promortion: "q"});

        if(move==null) return false;
        setGame(gameCopy);
        return true;
    }
// rendering the board 
    return (
        <div style={{ width: "420px" }}>
            <Chessboard
            position={game.fen()} // fen=universal chess ss format
            onPieceDrop={onPieceDrop}
            />
        </div>
    );

}
