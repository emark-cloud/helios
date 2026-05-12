// SPDX-License-Identifier: GPL-3.0
/*
    Copyright 2021 0KIMS association.

    This file is generated with [snarkJS](https://github.com/iden3/snarkjs).

    snarkJS is a free software: you can redistribute it and/or modify it
    under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    snarkJS is distributed in the hope that it will be useful, but WITHOUT
    ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
    or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public
    License for more details.

    You should have received a copy of the GNU General Public License
    along with snarkJS. If not, see <https://www.gnu.org/licenses/>.
*/

pragma solidity >=0.7.0 <0.9.0;

contract MomentumV1Verifier {
    // Scalar field size
    uint256 constant r    = 21888242871839275222246405745257275088548364400416034343698204186575808495617;
    // Base field size
    uint256 constant q   = 21888242871839275222246405745257275088696311157297823662689037894645226208583;

    // Verification Key data
    uint256 constant alphax  = 20491192805390485299153009773594534940189261866228447918068658471970481763042;
    uint256 constant alphay  = 9383485363053290200918347156157836566562967994039712273449902621266178545958;
    uint256 constant betax1  = 4252822878758300859123897981450591353533073413197771768651442665752259397132;
    uint256 constant betax2  = 6375614351688725206403948262868962793625744043794305715222011528459656738731;
    uint256 constant betay1  = 21847035105528745403288232691147584728191162732299865338377159692350059136679;
    uint256 constant betay2  = 10505242626370262277552901082094356697409835680220590971873171140371331206856;
    uint256 constant gammax1 = 11559732032986387107991004021392285783925812861821192530917403151452391805634;
    uint256 constant gammax2 = 10857046999023057135944570762232829481370756359578518086990519993285655852781;
    uint256 constant gammay1 = 4082367875863433681332203403145435568316851327593401208105741076214120093531;
    uint256 constant gammay2 = 8495653923123431417604973247489272438418190587263600148770280649306958101930;
    uint256 constant deltax1 = 14716327031164233914432871405457150211084909190319019846738640539401264063265;
    uint256 constant deltax2 = 18772734358361163788040829501310379495532681670367819245640150266534876839196;
    uint256 constant deltay1 = 10021398193376580341268747396835125363282994932310869645843580306227611911576;
    uint256 constant deltay2 = 18902462895260577238359754726544181686901347256668650163012040240832976584736;

    
    uint256 constant IC0x = 14485340958498515998178034897396991988025434800050225237206865965845225552088;
    uint256 constant IC0y = 18497244045056540451244721629307252430050347666114770963877955901603886855383;
    
    uint256 constant IC1x = 21182376400623139940740495967336263157831564833834733476839697230654877963567;
    uint256 constant IC1y = 11540447467700060968876182099074016502560448294589116022155494672644056853696;
    
    uint256 constant IC2x = 3345093992537341852762739827217317429528402710350615004818445173560639013013;
    uint256 constant IC2y = 17633024535466795789209002153755136243320875763901675313825600954310651981746;
    
    uint256 constant IC3x = 19655247968227373403934253121798339848457557091624577378539445110701774526165;
    uint256 constant IC3y = 20663918066466561334969864363010114629508168514758905851723941271472821477712;
    
    uint256 constant IC4x = 8573406284371350460524437598163507553120694007429202340217141680301240046939;
    uint256 constant IC4y = 9267910291038707769995907162512690795790307079308762351427845016855828795951;
    
    uint256 constant IC5x = 8464083517300528306319143762945093327523763049128614983469065685569650438255;
    uint256 constant IC5y = 10151724303013647408863757225696764812481552901122221297079775021869116364333;
    
    uint256 constant IC6x = 17901051646841609648448069386588926376170421153262729851416810539314915986389;
    uint256 constant IC6y = 20084442579803863828461302438844072005544513564839873115462331644722815913232;
    
    uint256 constant IC7x = 21448733647087216918970039975007255557005167726335514515382649767332104696682;
    uint256 constant IC7y = 21865786704837832064160056624312168627146354591643075811927379794168556267049;
    
    uint256 constant IC8x = 10960229711011529204537602407108205486003592368266744826015688270387323762115;
    uint256 constant IC8y = 7302591104502203668304383872099638590641081793746704602138353766081624056125;
    
    uint256 constant IC9x = 8988359295618027081312886317898775345688544448321056411535212394771545604226;
    uint256 constant IC9y = 19929017771979954336171419360058964784952472016615683002014551640078243059026;
    
    uint256 constant IC10x = 18801324185380708274146089183296067596790165578564940939790307592911569261891;
    uint256 constant IC10y = 18984607075490827996391118367535717502374120667433012051681721034885279912616;
    
    uint256 constant IC11x = 19993076427213695975748599101803931002680426426051539363709162559932118774531;
    uint256 constant IC11y = 2356058080448691499173567849858397485479178428217690489819414120178323862585;
    
    uint256 constant IC12x = 7076816899864292800268089353898378891014660911767980752936912849813310887386;
    uint256 constant IC12y = 13071332558167377583667332388342447896560370028725527677009750896231175316047;
    
    uint256 constant IC13x = 20997064999208437475223479572142176417863648809194832931014308888294731095272;
    uint256 constant IC13y = 16000219876816065599152404792680155832799478107809270372866494056783563870655;
    
    uint256 constant IC14x = 3326687020470531677962448749510207505284471782161769096613860222111041520774;
    uint256 constant IC14y = 7938529451172502927588659768840598122964085912735348660196875268948906713409;
    
    uint256 constant IC15x = 12520111228204452720986167081604821105398733447712569310937091658519690882272;
    uint256 constant IC15y = 4745852742999859909704609192837872140059615157649092668567636862780644205287;
    
    uint256 constant IC16x = 20614297103661610951604338292983182799094793491890856841613403041615327755151;
    uint256 constant IC16y = 8535480923302417376211981514198665460492227050530849371234324399823039539072;
    
 
    // Memory data
    uint16 constant pVk = 0;
    uint16 constant pPairing = 128;

    uint16 constant pLastMem = 896;

    function verifyProof(uint[2] calldata _pA, uint[2][2] calldata _pB, uint[2] calldata _pC, uint[16] calldata _pubSignals) public view returns (bool) {
        assembly {
            function checkField(v) {
                if iszero(lt(v, r)) {
                    mstore(0, 0)
                    return(0, 0x20)
                }
            }
            
            // G1 function to multiply a G1 value(x,y) to value in an address
            function g1_mulAccC(pR, x, y, s) {
                let success
                let mIn := mload(0x40)
                mstore(mIn, x)
                mstore(add(mIn, 32), y)
                mstore(add(mIn, 64), s)

                success := staticcall(sub(gas(), 2000), 7, mIn, 96, mIn, 64)

                if iszero(success) {
                    mstore(0, 0)
                    return(0, 0x20)
                }

                mstore(add(mIn, 64), mload(pR))
                mstore(add(mIn, 96), mload(add(pR, 32)))

                success := staticcall(sub(gas(), 2000), 6, mIn, 128, pR, 64)

                if iszero(success) {
                    mstore(0, 0)
                    return(0, 0x20)
                }
            }

            function checkPairing(pA, pB, pC, pubSignals, pMem) -> isOk {
                let _pPairing := add(pMem, pPairing)
                let _pVk := add(pMem, pVk)

                mstore(_pVk, IC0x)
                mstore(add(_pVk, 32), IC0y)

                // Compute the linear combination vk_x
                
                g1_mulAccC(_pVk, IC1x, IC1y, calldataload(add(pubSignals, 0)))
                
                g1_mulAccC(_pVk, IC2x, IC2y, calldataload(add(pubSignals, 32)))
                
                g1_mulAccC(_pVk, IC3x, IC3y, calldataload(add(pubSignals, 64)))
                
                g1_mulAccC(_pVk, IC4x, IC4y, calldataload(add(pubSignals, 96)))
                
                g1_mulAccC(_pVk, IC5x, IC5y, calldataload(add(pubSignals, 128)))
                
                g1_mulAccC(_pVk, IC6x, IC6y, calldataload(add(pubSignals, 160)))
                
                g1_mulAccC(_pVk, IC7x, IC7y, calldataload(add(pubSignals, 192)))
                
                g1_mulAccC(_pVk, IC8x, IC8y, calldataload(add(pubSignals, 224)))
                
                g1_mulAccC(_pVk, IC9x, IC9y, calldataload(add(pubSignals, 256)))
                
                g1_mulAccC(_pVk, IC10x, IC10y, calldataload(add(pubSignals, 288)))
                
                g1_mulAccC(_pVk, IC11x, IC11y, calldataload(add(pubSignals, 320)))
                
                g1_mulAccC(_pVk, IC12x, IC12y, calldataload(add(pubSignals, 352)))
                
                g1_mulAccC(_pVk, IC13x, IC13y, calldataload(add(pubSignals, 384)))
                
                g1_mulAccC(_pVk, IC14x, IC14y, calldataload(add(pubSignals, 416)))
                
                g1_mulAccC(_pVk, IC15x, IC15y, calldataload(add(pubSignals, 448)))
                
                g1_mulAccC(_pVk, IC16x, IC16y, calldataload(add(pubSignals, 480)))
                

                // -A
                mstore(_pPairing, calldataload(pA))
                mstore(add(_pPairing, 32), mod(sub(q, calldataload(add(pA, 32))), q))

                // B
                mstore(add(_pPairing, 64), calldataload(pB))
                mstore(add(_pPairing, 96), calldataload(add(pB, 32)))
                mstore(add(_pPairing, 128), calldataload(add(pB, 64)))
                mstore(add(_pPairing, 160), calldataload(add(pB, 96)))

                // alpha1
                mstore(add(_pPairing, 192), alphax)
                mstore(add(_pPairing, 224), alphay)

                // beta2
                mstore(add(_pPairing, 256), betax1)
                mstore(add(_pPairing, 288), betax2)
                mstore(add(_pPairing, 320), betay1)
                mstore(add(_pPairing, 352), betay2)

                // vk_x
                mstore(add(_pPairing, 384), mload(add(pMem, pVk)))
                mstore(add(_pPairing, 416), mload(add(pMem, add(pVk, 32))))


                // gamma2
                mstore(add(_pPairing, 448), gammax1)
                mstore(add(_pPairing, 480), gammax2)
                mstore(add(_pPairing, 512), gammay1)
                mstore(add(_pPairing, 544), gammay2)

                // C
                mstore(add(_pPairing, 576), calldataload(pC))
                mstore(add(_pPairing, 608), calldataload(add(pC, 32)))

                // delta2
                mstore(add(_pPairing, 640), deltax1)
                mstore(add(_pPairing, 672), deltax2)
                mstore(add(_pPairing, 704), deltay1)
                mstore(add(_pPairing, 736), deltay2)


                let success := staticcall(sub(gas(), 2000), 8, _pPairing, 768, _pPairing, 0x20)

                isOk := and(success, mload(_pPairing))
            }

            let pMem := mload(0x40)
            mstore(0x40, add(pMem, pLastMem))

            // Validate that all evaluations ∈ F
            
            checkField(calldataload(add(_pubSignals, 0)))
            
            checkField(calldataload(add(_pubSignals, 32)))
            
            checkField(calldataload(add(_pubSignals, 64)))
            
            checkField(calldataload(add(_pubSignals, 96)))
            
            checkField(calldataload(add(_pubSignals, 128)))
            
            checkField(calldataload(add(_pubSignals, 160)))
            
            checkField(calldataload(add(_pubSignals, 192)))
            
            checkField(calldataload(add(_pubSignals, 224)))
            
            checkField(calldataload(add(_pubSignals, 256)))
            
            checkField(calldataload(add(_pubSignals, 288)))
            
            checkField(calldataload(add(_pubSignals, 320)))
            
            checkField(calldataload(add(_pubSignals, 352)))
            
            checkField(calldataload(add(_pubSignals, 384)))
            
            checkField(calldataload(add(_pubSignals, 416)))
            
            checkField(calldataload(add(_pubSignals, 448)))
            
            checkField(calldataload(add(_pubSignals, 480)))
            

            // Validate all evaluations
            let isValid := checkPairing(_pA, _pB, _pC, _pubSignals, pMem)

            mstore(0, isValid)
             return(0, 0x20)
         }
     }
 }
